"""Additional coverage for project setup and related paths."""

import io
import json
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

from spell_sync.application import SpellSyncService
from spell_sync.application.events import OperationKind, PresentedEvent
from spell_sync.application.operation_reports import build_setup_operation_report
from spell_sync.application.reports import OperationOutcome
from spell_sync.bundled_files import bundled_path
from spell_sync.cli_options import CliOptions
from spell_sync.commands import cmd_init
from spell_sync.project_setup.discovery import discover_setup_targets
from spell_sync.project_setup.draft import SetupDraft
from spell_sync.project_setup.execute import (
    ProjectSetupExecution,
    ProjectSetupOutcome,
    execute_project_setup,
)
from spell_sync.project_setup.prepare import SetupFileAction, prepare_project_setup
from spell_sync.project_setup.state import (
    ProjectSetupStatus,
    inspect_existing_wordlist,
    inspect_project_setup,
    validate_setup_wordlist,
)
from spell_sync.push_journal import (
    JournalLoadStatus,
    safe_discard_journal_file,
    safe_discard_txn_snapshots,
)
from spell_sync.settings import ConfigLoadResult, ConfigStatus


class TestProjectSetupCoverage(unittest.TestCase):
    def _setup_project(self, root: Path) -> None:
        wordlist = root / "wordlist.txt"
        prepared = prepare_project_setup(SetupDraft(wordlist, (), create_wordlist=True))
        execute_project_setup(prepared, confirmed_setup_id=prepared.setup_id)

    def test_prepare_project_setup_creates_files(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_project(root)
            self.assertTrue((root / "wordlist.txt").is_file())
            self.assertTrue((root / "spell-sync.toml").is_file())
            self.assertTrue(bundled_path("wordlist.txt.example").is_file())

    def test_cmd_init_existing_project_is_noop(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup_project(root)
            previous = os.getcwd()
            try:
                os.chdir(root)
                code = cmd_init(CliOptions())
            finally:
                os.chdir(previous)
            self.assertEqual(code, 0)

    def test_service_setup_emits_events(self):
        import tempfile

        service = SpellSyncService()
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            draft = SetupDraft(wordlist, (), create_wordlist=True)
            prepared = service.prepare_project_setup(draft)
            events: list[PresentedEvent] = []

            def sink(event: PresentedEvent) -> None:
                events.append(event)

            service.execute_project_setup(
                prepared,
                confirmed_setup_id=prepared.setup_id,
                event_sink=sink,
            )
            self.assertTrue(events)
            self.assertEqual(events[0].operation, OperationKind.SETUP)

    def test_execute_invalid_created_config_rolls_back(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            prepared = prepare_project_setup(SetupDraft(wordlist, (), create_wordlist=True))
            with patch(
                "spell_sync.project_setup.execute.load_config_result",
                lambda **kwargs: ConfigLoadResult(ConfigStatus.SYNTAX_ERROR, None, ()),
            ):
                execution = execute_project_setup(
                    prepared,
                    confirmed_setup_id=prepared.setup_id,
                )
            self.assertIn(
                execution.outcome,
                {ProjectSetupOutcome.FAILED, ProjectSetupOutcome.SETUP_INCOMPLETE},
            )

    def test_safe_discard_rejects_symlink_journal(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            wordlist = project / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal = project / ".spell-sync.journal.json"
            journal.write_text("{}", encoding="utf-8")
            journal.unlink()
            journal.symlink_to("/etc/hosts")
            ok, detail = safe_discard_journal_file(wordlist)
            self.assertFalse(ok)
            self.assertIsNotNone(detail)
            self.assertNotIn("/etc/hosts", detail or "")
            self.assertNotIn("/", detail or "")

    def test_safe_discard_rejects_bad_snapshot_path(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            wordlist = project / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            ok, detail = safe_discard_txn_snapshots(
                wordlist,
                "00000000-0000-4000-8000-000000000001",
                str(Path(tmp) / "outside"),
            )
            self.assertFalse(ok)
            self.assertIsNotNone(detail)

    def test_discard_journal_raises_on_failure(self):
        import tempfile

        from spell_sync.secure_artifacts import SecureArtifactError

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            wordlist = project / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal = project / ".spell-sync.journal.json"
            journal.write_text('{"schema_version":2}\n', encoding="utf-8")
            with patch(
                "spell_sync.push_journal.remove_trusted_file",
                side_effect=SecureArtifactError("unlink_failed", "nope"),
            ):
                ok, detail = safe_discard_journal_file(wordlist)
            self.assertFalse(ok)
            self.assertEqual(detail, "unlink_failed")
            self.assertNotIn("nope", detail or "")

    def test_cmd_init_json_when_project_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            prepared = prepare_project_setup(SetupDraft(wordlist, (), create_wordlist=True))
            execute_project_setup(prepared, confirmed_setup_id=prepared.setup_id)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cmd_init(CliOptions(json_output=True, wordlist=str(wordlist)))
            self.assertEqual(code, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["outcome"], "stopped_safely")

    def test_cmd_init_failure_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            prepared = prepare_project_setup(SetupDraft(wordlist, (), create_wordlist=True))
            with patch.object(SpellSyncService, "prepare_project_setup", return_value=prepared):
                with patch.object(
                    SpellSyncService,
                    "execute_project_setup",
                    return_value=ProjectSetupExecution(
                        prepared=prepared,
                        outcome=ProjectSetupOutcome.FAILED,
                        message="boom",
                    ),
                ):
                    code = cmd_init(CliOptions(wordlist=str(wordlist)))
            self.assertNotEqual(code, 0)

    def test_stale_home_config_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            config_dir = home / ".config" / "spell-sync"
            config_dir.mkdir(parents=True)
            (config_dir / "spell-sync.toml").write_text("[push]\n", encoding="utf-8")
            project = Path(tmp) / "project"
            project.mkdir()
            wordlist = project / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            (project / "spell-sync.toml").write_text("[push]\n", encoding="utf-8")
            with patch.dict("os.environ", {"HOME": str(home)}, clear=False):
                state = inspect_project_setup(
                    wordlist,
                    allow_project_creation=False,
                )
            self.assertEqual(state.status, ProjectSetupStatus.READY)
            from spell_sync.settings import project_config_path

            path = project_config_path(wordlist)
            self.assertEqual(path, (project / "spell-sync.toml").resolve())
            self.assertNotIn(".config", str(path))

    def test_validate_existing_unreadable_wordlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            wordlist.chmod(0)
            try:
                with self.assertRaises(ValueError):
                    validate_setup_wordlist(str(wordlist))
            finally:
                wordlist.chmod(stat.S_IWUSR | stat.S_IRUSR)

    def test_inspect_existing_wordlist_missing(self):
        count, status, detail = inspect_existing_wordlist(Path("/no/such/file.txt"))
        self.assertIsNone(count)
        self.assertIsNone(status)
        self.assertIsNone(detail)

    def test_prepare_missing_wordlist_without_create(self):
        prepared = prepare_project_setup(
            SetupDraft(Path("/tmp/none/wordlist.txt"), (), create_wordlist=False)
        )
        self.assertFalse(prepared.can_execute)

    def test_execute_when_project_directory_already_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "project" / "wordlist.txt"
            project = wordlist.parent
            project.mkdir()
            (project / ".spell-sync.lock").write_text("locked\n", encoding="utf-8")
            prepared = prepare_project_setup(SetupDraft(wordlist, (), create_wordlist=True))
            execution = execute_project_setup(
                prepared,
                confirmed_setup_id=prepared.setup_id,
            )
            self.assertEqual(execution.outcome, ProjectSetupOutcome.COMPLETED)

    def test_execute_low_level_event_sink(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            prepared = prepare_project_setup(SetupDraft(wordlist, (), create_wordlist=True))
            from spell_sync.application.events import EventId, TechnicalEvent

            event_ids: list[EventId] = []

            def sink(event: TechnicalEvent) -> None:
                event_ids.append(event.event_id)

            execute_project_setup(
                prepared,
                confirmed_setup_id=prepared.setup_id,
                event_sink=sink,
            )
            self.assertIn(EventId.SETUP_COMPLETED, event_ids)

    def test_build_setup_report_existing_wordlist(self):
        prepared = prepare_project_setup(
            SetupDraft(Path("/tmp/keep/wordlist.txt"), (), create_wordlist=True)
        )
        prepared = replace(prepared, existing_wordlist_kept=True)
        report = build_setup_operation_report(
            ProjectSetupExecution(
                prepared=prepared,
                outcome=ProjectSetupOutcome.COMPLETED,
                message="ok",
            )
        )
        self.assertIn("kept unchanged", " ".join(report.details))

    def test_discover_macos_spelling_family(self):
        import sys

        rows = discover_setup_targets().targets
        present = any(row.identifier == "macos_spelling" for row in rows)
        if sys.platform == "darwin":
            self.assertTrue(present)
        else:
            self.assertFalse(present)

    def test_service_validate_setup_wordlist(self):
        service = SpellSyncService()
        path, detail = service.validate_setup_wordlist("~/my-words/wordlist.txt")
        self.assertIsNotNone(path)
        self.assertIsNotNone(detail)

    def test_service_discover_and_prepare_setup(self):
        service = SpellSyncService()
        draft = SetupDraft(Path("/tmp/svc/wordlist.txt"), ("chrome",), create_wordlist=True)
        discovery = service.discover_setup_targets(draft)
        self.assertTrue(discovery.targets)
        prepared = service.prepare_project_setup(draft)
        self.assertTrue(prepared.can_execute)

    def test_inspect_project_setup_unknown_state(self):
        with patch(
            "spell_sync.project_setup.state.load_config_result",
            return_value=MagicMock(status=ConfigStatus.VALID, config={}, diagnostics=()),
        ):
            with patch(
                "spell_sync.project_setup.state.load_journal_result",
                return_value=MagicMock(status=JournalLoadStatus.ABSENT),
            ):
                state = inspect_project_setup(
                    Path("/tmp/unknown/wordlist.txt"),
                    allow_project_creation=False,
                )
        self.assertEqual(state.status, ProjectSetupStatus.MISSING_PROJECT)

    def test_execute_stopped_when_can_execute_false(self):
        prepared = prepare_project_setup(
            SetupDraft(Path("/tmp/x/wordlist.txt"), (), create_wordlist=True)
        )
        prepared = replace(prepared, can_execute=False)
        execution = execute_project_setup(
            prepared,
            confirmed_setup_id=prepared.setup_id,
        )
        self.assertEqual(execution.outcome, ProjectSetupOutcome.STOPPED_SAFELY)

    def test_execute_conflict_at_start(self):
        prepared = prepare_project_setup(
            SetupDraft(Path("/tmp/y/wordlist.txt"), (), create_wordlist=True)
        )
        conflicted = replace(
            prepared,
            files=tuple(
                replace(item, action=SetupFileAction.CONFLICT)
                if item.relative_name == "spell-sync.toml"
                else item
                for item in prepared.files
            ),
        )
        execution = execute_project_setup(
            conflicted,
            confirmed_setup_id=conflicted.setup_id,
        )
        self.assertEqual(execution.outcome, ProjectSetupOutcome.STOPPED_SAFELY)

    def test_rollback_created_oserror(self):
        from spell_sync.project_setup.execute import _rollback_created

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "created.txt"
            path.write_text("x", encoding="utf-8")
            with patch.object(Path, "unlink", side_effect=OSError("busy")):
                leftover = _rollback_created([path])
            self.assertTrue(leftover)

    def test_discover_unreadable_and_corrupt_targets(self):
        from spell_sync.project_setup import discovery as discovery_mod
        from spell_sync.read_outcome import ReadStatus

        dictionary = MagicMock()
        dictionary.name = "chrome:Default"
        dictionary.path = "/tmp/chrome.txt"
        dictionary.format = MagicMock(value="text")
        result_ok = MagicMock(status=ReadStatus.OK, words=["a"], detail=None)
        result_corrupt = MagicMock(status=ReadStatus.CORRUPT, words=None, detail="bad")
        result_unreadable = MagicMock(status=ReadStatus.UNREADABLE, words=None, detail="nope")
        with patch.object(discovery_mod, "discover_dictionaries", return_value=[dictionary]):
            with patch.object(
                discovery_mod,
                "dictionary_read_result",
                side_effect=[result_corrupt, result_unreadable, result_ok],
            ):
                rows = discovery_mod.discover_setup_targets().targets
        self.assertTrue(rows)

    def test_validate_setup_wordlist_with_existing_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            (Path(tmp) / "spell-sync.toml").write_text("[push]\n", encoding="utf-8")
            _path, detail = validate_setup_wordlist(str(wordlist))
            self.assertIn("Existing config detected", detail or "")

    def test_normalize_wordlist_parent_file_error(self):
        from spell_sync.project_setup.state import normalize_wordlist_input

        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "file"
            parent.write_text("x", encoding="utf-8")
            with self.assertRaises(ValueError):
                normalize_wordlist_input(str(parent / "wordlist.txt"))

    def test_inspect_existing_wordlist_unreadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            wordlist.chmod(0)
            try:
                count, _status, _detail = inspect_existing_wordlist(wordlist)
            finally:
                wordlist.chmod(stat.S_IWUSR | stat.S_IRUSR)
            self.assertIsNone(count)

    def test_service_build_setup_report(self):
        prepared = prepare_project_setup(
            SetupDraft(Path("/tmp/report/wordlist.txt"), (), create_wordlist=True)
        )
        execution = ProjectSetupExecution(
            prepared=prepared,
            outcome=ProjectSetupOutcome.COMPLETED,
            message="ok",
        )
        report = SpellSyncService().build_setup_report(execution)
        self.assertEqual(report.outcome, OperationOutcome.COMPLETED)

    def test_discover_family_and_empty_group_helpers(self):
        from spell_sync.project_setup import discovery as discovery_mod
        from spell_sync.read_outcome import ReadStatus

        win_dictionary = MagicMock()
        win_dictionary.name = "win-10"
        self.assertEqual(discovery_mod._family_id(win_dictionary), "win_spelling")
        self.assertEqual(
            discovery_mod._iter_target_groups({"orphan": [], "chrome": [win_dictionary]}),
            [("chrome", [win_dictionary])],
        )
        self.assertEqual(discovery_mod._iter_target_groups({"orphan": []}), [])

        dictionary = MagicMock()
        dictionary.name = "chrome:Default"
        dictionary.path = "/tmp/chrome.txt"
        dictionary.format = MagicMock(value="text")
        empty_result = MagicMock(status=ReadStatus.EMPTY, words=[], detail=None)
        with patch.object(discovery_mod, "discover_dictionaries", return_value=[dictionary]):
            with patch.object(
                discovery_mod,
                "dictionary_read_result",
                return_value=empty_result,
            ):
                rows = discovery_mod.discover_setup_targets().targets
        self.assertEqual(rows[0].status, ReadStatus.EMPTY.value)
        self.assertTrue(rows[0].available)

    def test_cmd_init_completed_with_empty_created_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            prepared = prepare_project_setup(SetupDraft(wordlist, (), create_wordlist=True))
            with patch.object(SpellSyncService, "prepare_project_setup", return_value=prepared):
                with patch.object(
                    SpellSyncService,
                    "execute_project_setup",
                    return_value=ProjectSetupExecution(
                        prepared=prepared,
                        outcome=ProjectSetupOutcome.COMPLETED,
                        message="ok",
                        created_files=(),
                    ),
                ):
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        code = cmd_init(CliOptions(wordlist=str(wordlist)))
            self.assertEqual(code, 0)
            self.assertIn("already has a Spell Sync project", buf.getvalue())

    def test_execute_file_exists_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            prepared = prepare_project_setup(SetupDraft(wordlist, (), create_wordlist=True))
            with patch(
                "spell_sync.project_setup.execute.atomic_write",
                side_effect=FileExistsError("/secret/wordlist.txt"),
            ):
                execution = execute_project_setup(
                    prepared,
                    confirmed_setup_id=prepared.setup_id,
                )
            self.assertEqual(execution.outcome, ProjectSetupOutcome.STOPPED_SAFELY)
            self.assertIn("already exists", execution.message)
            self.assertNotIn("/secret/", execution.message)

    def test_execute_creates_nested_project_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "nested" / "project" / "wordlist.txt"
            prepared = prepare_project_setup(SetupDraft(wordlist, (), create_wordlist=True))
            extra_dir = wordlist.parent / "setup-artifacts"
            prepared = replace(
                prepared,
                directories_to_create=(wordlist.parent, extra_dir),
            )
            execution = execute_project_setup(
                prepared,
                confirmed_setup_id=prepared.setup_id,
            )
            self.assertEqual(execution.outcome, ProjectSetupOutcome.COMPLETED)
            self.assertTrue(wordlist.is_file())
            self.assertTrue(extra_dir.is_dir())

    def test_execute_skips_existing_project_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "nested" / "wordlist.txt"
            prepared = prepare_project_setup(SetupDraft(wordlist, (), create_wordlist=True))
            wordlist.parent.mkdir(parents=True)
            prepared = replace(prepared, directories_to_create=(wordlist.parent,))
            execution = execute_project_setup(
                prepared,
                confirmed_setup_id=prepared.setup_id,
            )
            self.assertEqual(execution.outcome, ProjectSetupOutcome.COMPLETED)

    def test_fingerprint_matches_without_fingerprint(self):
        from spell_sync.project_setup.execute import _fingerprint_matches

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wordlist.txt"
            self.assertTrue(_fingerprint_matches(path, None))
            path.write_text("alpha\n", encoding="utf-8")
            self.assertFalse(_fingerprint_matches(path, None))

    def test_inspect_project_setup_unresolved_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            config = Path(tmp) / "spell-sync.toml"
            wordlist.write_text("alpha\n", encoding="utf-8")
            config.write_text("[push]\n", encoding="utf-8")
            with patch(
                "spell_sync.project_setup.state.load_config_result",
                return_value=MagicMock(status=ConfigStatus.ABSENT, config=None, diagnostics=()),
            ):
                with patch(
                    "spell_sync.project_setup.state.load_journal_result",
                    return_value=MagicMock(status=JournalLoadStatus.ABSENT),
                ):
                    state = inspect_project_setup(
                        wordlist,
                        allow_project_creation=False,
                    )
            self.assertEqual(state.status, ProjectSetupStatus.MISSING_PROJECT)
            self.assertIn("could not be determined", state.detail or "")

    def test_normalize_wordlist_empty_filename(self):
        from spell_sync.project_setup.state import normalize_wordlist_input

        with self.assertRaises(ValueError):
            normalize_wordlist_input(".")

        fake = MagicMock()
        fake.exists.return_value = False
        fake.is_dir.return_value = False
        fake.name = "."
        fake.parent = MagicMock(exists=lambda: False, is_file=lambda: False)
        with patch.object(Path, "expanduser", return_value=fake):
            with self.assertRaises(ValueError):
                normalize_wordlist_input("ignored")

    def test_discovery_macos_family_and_unknown_selectable(self):
        from spell_sync.dictionaries import Dictionary, DictionaryFormat
        from spell_sync.project_setup import discovery as discovery_module
        from spell_sync.read_outcome import ReadStatus

        macos_dict = Dictionary(
            name="macos-en",
            path="/tmp/macos-en",
            format=DictionaryFormat.TEXT,
        )
        self.assertEqual(discovery_module._family_id(macos_dict), "macos_spelling")
        classic = Dictionary(
            name="macos",
            path="/tmp/LocalDictionary",
            format=DictionaryFormat.TEXT,
        )
        self.assertEqual(discovery_module.dictionary_family_id(classic.name), "macos_spelling")
        self.assertFalse(
            discovery_module._target_selectable(
                identifier="not-a-config-target",
                detected=True,
                available=True,
                readable=True,
                supported=True,
                status=ReadStatus.OK,
                ambiguous=False,
            )
        )
        self.assertTrue(
            discovery_module._target_selectable(
                identifier="sublime",
                detected=True,
                available=True,
                readable=True,
                supported=True,
                status=ReadStatus.OK,
                ambiguous=False,
            )
        )


if __name__ == "__main__":
    unittest.main()
