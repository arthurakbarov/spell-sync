"""Targeted tests for remaining uncovered lines."""

from __future__ import annotations

import io
import json
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

from spell_sync.application import SpellSyncService
from spell_sync.application.builders import build_setup_operation_report
from spell_sync.application.reports import (
    OperationOutcome,
    OperationReport,
    RecoveryOutcome,
    RecoveryStatus,
)
from spell_sync.application.requests import (
    ProjectRef,
    RecoveryRequest,
)
from spell_sync.bundled_files import init_project_directory
from spell_sync.cli_options import CliOptions
from spell_sync.commands import cmd_init
from spell_sync.exit_codes import ExitCode
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
    JOURNAL_STATE_COMPLETED,
    DiscardArtifactsResult,
    JournalLoadStatus,
    RecoverResult,
    cleanup_after_successful_recovery,
    discard_completed_journal,
    discard_txn_snapshots,
    safe_discard_journal_file,
    safe_discard_txn_snapshots,
)
from spell_sync.settings import ConfigStatus
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.dashboard import DashboardScreen
from spell_sync.tui.screens.report_screen import ReportScreen
from tests.journal_test_utils import write_test_journal
from tests.tui.fake_service import fake_service, sample_recovery_preview


class TestRemainingCoverage(unittest.TestCase):
    def test_cmd_init_json_when_project_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_directory(root)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cmd_init(CliOptions(json_output=True, wordlist=str(root / "wordlist.txt")))
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

    def test_ambiguous_project_detection(self):
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
            self.assertEqual(state.status, ProjectSetupStatus.AMBIGUOUS_PROJECT)

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
        rows = discover_setup_targets().targets
        self.assertTrue(any(row.identifier == "macos_spelling" for row in rows))

    def test_cleanup_after_successful_recovery_snapshot_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal = write_test_journal(
                wordlist,
                state=JOURNAL_STATE_COMPLETED,
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            with patch(
                "spell_sync.push_journal.safe_discard_txn_snapshots",
                return_value=(False, "bad snap"),
            ):
                result = cleanup_after_successful_recovery(journal)
            self.assertFalse(result.ok)

    def test_discard_completed_journal_journal_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            write_test_journal(
                wordlist,
                state=JOURNAL_STATE_COMPLETED,
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            with patch(
                "spell_sync.push_journal.safe_discard_txn_snapshots",
                return_value=(True, None),
            ):
                with patch(
                    "spell_sync.push_journal.safe_discard_journal_file",
                    return_value=(False, "journal stuck"),
                ):
                    result = discard_completed_journal(wordlist)
            self.assertFalse(result.ok)
            self.assertTrue(result.snapshots_removed)

    def test_safe_discard_txn_snapshots_bad_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            ok, detail = safe_discard_txn_snapshots(
                wordlist,
                "00000000-0000-4000-8000-000000000001",
                str(Path(tmp) / "outside"),
            )
            self.assertFalse(ok)
            self.assertIsNotNone(detail)

    def test_service_validate_setup_wordlist(self):
        service = SpellSyncService()
        path, detail = service.validate_setup_wordlist("~/spell-words/wordlist.txt")
        self.assertIsNotNone(path)
        self.assertIsNotNone(detail)

    def test_service_discover_and_prepare_setup(self):
        service = SpellSyncService()
        draft = SetupDraft(Path("/tmp/svc/wordlist.txt"), ("chrome",), create_wordlist=True)
        discovery = service.discover_setup_targets(draft)
        self.assertTrue(discovery.targets)
        prepared = service.prepare_project_setup(draft)
        self.assertTrue(prepared.can_execute)

    def test_recovery_cleanup_failure_after_success(self):
        service = SpellSyncService()
        preview = sample_recovery_preview(status=RecoveryStatus.RECOVERABLE)
        with patch(
            "spell_sync.application._operation_deps.recover_from_journal",
            return_value=RecoverResult(("wordlist",), (), ()),
        ):
            with patch(
                "spell_sync.application._operation_deps.cleanup_after_successful_recovery",
                return_value=DiscardArtifactsResult(False, False, "cleanup failed"),
            ):
                with patch(
                    "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
                ) as scope:
                    scope.return_value.__enter__.return_value = MagicMock(
                        journal_result=MagicMock(
                            status=JournalLoadStatus.VALID_IN_PROGRESS,
                            journal=MagicMock(transaction_id=preview.transaction_id),
                        )
                    )
                    scope.return_value.__exit__.return_value = False
                    execution = service.execute_recovery(
                        RecoveryRequest(project=ProjectRef()),
                        preview,
                        confirmed_transaction_id=preview.preview_fingerprint,
                    )
        self.assertEqual(execution.outcome, RecoveryOutcome.RECOVERY_INCOMPLETE)

    def test_recovery_discard_corrupt_journal_failure(self):
        service = SpellSyncService()
        preview = sample_recovery_preview(
            status=RecoveryStatus.CORRUPT_JOURNAL,
            can_discard=True,
            can_recover=False,
        )
        with patch(
            "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
        ) as scope:
            scope.return_value.__enter__.return_value = MagicMock(
                context=MagicMock(wordlist_file=Path("/tmp/w.txt"))
            )
            scope.return_value.__exit__.return_value = False
            with patch(
                "spell_sync.application._operation_deps.safe_discard_journal_file",
                return_value=(False, "nope"),
            ):
                execution = service.execute_recovery_discard(
                    RecoveryRequest(project=ProjectRef()),
                    preview,
                    confirmed_transaction_id=preview.preview_fingerprint,
                )
        self.assertEqual(execution.outcome, RecoveryOutcome.FAILED)

    def test_controller_clear_setup_session(self):
        controller = TuiController(fake_service(), CliOptions())
        controller.set_setup_wordlist(Path("/tmp/w.txt"))
        controller.clear_setup_session()
        with self.assertRaises(RuntimeError):
            controller.prepare_setup_preview()

    def test_setup_report_dashboard_branch(self):
        report = OperationReport(
            operation="setup",
            outcome=OperationOutcome.COMPLETED,
            title="Project created",
            summary="done",
            details=(),
        )
        controller = TuiController(fake_service(), CliOptions())
        screen = ReportScreen(controller, report)

        class FakeApp:
            def __init__(self) -> None:
                self.screen_stack = [MagicMock(), MagicMock()]
                self.screen = self.screen_stack[-1]

            def pop_screen(self) -> None:
                self.screen_stack.pop()

            def push_screen(self, pushed) -> None:
                self.screen = pushed
                self.screen_stack.append(pushed)

        fake_app = FakeApp()
        with patch.object(DashboardScreen, "action_refresh_dashboard") as refresh:
            with patch.object(ReportScreen, "app", new_callable=PropertyMock) as app_prop:
                app_prop.return_value = fake_app
                screen.action_back_dashboard()
        refresh.assert_called_once()

    def test_cleanup_after_successful_recovery_journal_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal = write_test_journal(
                wordlist,
                state=JOURNAL_STATE_COMPLETED,
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            with patch(
                "spell_sync.push_journal.safe_discard_txn_snapshots",
                return_value=(True, None),
            ):
                with patch(
                    "spell_sync.push_journal.safe_discard_journal_file",
                    return_value=(False, "journal stuck"),
                ):
                    result = cleanup_after_successful_recovery(journal)
            self.assertFalse(result.ok)
            self.assertTrue(result.snapshots_removed)

    def test_safe_discard_snapshot_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal = write_test_journal(
                wordlist,
                state=JOURNAL_STATE_COMPLETED,
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            snap = Path(journal.snapshot_dir)
            outside = Path(tmp) / "outside"
            outside.mkdir()
            if snap.exists():
                for child in snap.iterdir():
                    child.unlink()
                snap.rmdir()
            snap.symlink_to(outside, target_is_directory=True)
            ok, detail = safe_discard_txn_snapshots(
                wordlist,
                journal.transaction_id,
                journal.snapshot_dir,
            )
            self.assertFalse(ok)
            self.assertIn("symlink", detail or "")

    def test_safe_discard_snapshot_rmtree_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal = write_test_journal(
                wordlist,
                state=JOURNAL_STATE_COMPLETED,
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            with patch("spell_sync.push_journal.remove_trusted_tree", side_effect=OSError("busy")):
                ok, detail = safe_discard_txn_snapshots(
                    wordlist,
                    journal.transaction_id,
                    journal.snapshot_dir,
                )
            self.assertFalse(ok)

    def test_safe_discard_journal_outside_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "project" / "wordlist.txt"
            wordlist.parent.mkdir()
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal = wordlist.parent / ".spell-sync.journal.json"
            journal.write_text("{}", encoding="utf-8")
            journal.unlink()
            journal.symlink_to(Path(tmp) / "outside")
            (Path(tmp) / "outside").write_text("{}", encoding="utf-8")
            ok, detail = safe_discard_journal_file(wordlist)
            self.assertFalse(ok)

    def test_discard_txn_snapshots_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            snap = wordlist.parent / ".spell-sync.txn" / "abc"
            snap.mkdir(parents=True)
            (snap / "file.snap").write_text("x", encoding="utf-8")
            discard_txn_snapshots(snap, wordlist=wordlist)
            self.assertFalse(snap.exists())

    def test_discard_completed_journal_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            result = discard_completed_journal(wordlist)
            self.assertFalse(result.ok)

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
            self.assertIn("already exist", buf.getvalue())

    def test_recovery_cleanup_discard_failure(self):
        service = SpellSyncService()
        preview = sample_recovery_preview(status=RecoveryStatus.COMPLETED_CLEANUP_PENDING)
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            write_test_journal(
                wordlist,
                state=JOURNAL_STATE_COMPLETED,
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            with patch(
                "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
            ) as scope:
                scope.return_value.__enter__.return_value = MagicMock(
                    context=MagicMock(wordlist_file=wordlist),
                    journal_result=MagicMock(status=JournalLoadStatus.VALID_COMPLETED),
                )
                scope.return_value.__exit__.return_value = False
                with patch(
                    "spell_sync.application._operation_deps.discard_completed_journal",
                    return_value=DiscardArtifactsResult(False, False, "failed"),
                ):
                    execution = service.execute_recovery_cleanup(
                        RecoveryRequest(project=ProjectRef(wordlist=wordlist)),
                        preview,
                        confirmed_transaction_id=preview.preview_fingerprint,
                    )
            self.assertEqual(execution.outcome, RecoveryOutcome.FAILED)

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
                count, status, detail = inspect_existing_wordlist(wordlist)
            finally:
                wordlist.chmod(stat.S_IWUSR | stat.S_IRUSR)
            self.assertIsNone(count)

    def test_discard_txn_snapshots_none(self):
        discard_txn_snapshots(None, wordlist=None)

    def test_safe_discard_snapshot_missing_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal = write_test_journal(
                wordlist,
                state=JOURNAL_STATE_COMPLETED,
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            snap = Path(journal.snapshot_dir)
            snap_file = snap.with_suffix(".snap-file")
            if snap.is_dir():
                for child in snap.iterdir():
                    child.unlink()
                snap.rmdir()
            snap_file.write_text("x", encoding="utf-8")
            ok, detail = safe_discard_txn_snapshots(
                wordlist,
                journal.transaction_id,
                str(snap_file),
            )
            self.assertFalse(ok)

    def test_execute_file_exists_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            prepared = prepare_project_setup(SetupDraft(wordlist, (), create_wordlist=True))
            with patch(
                "spell_sync.project_setup.execute.atomic_write",
                side_effect=FileExistsError("exists"),
            ):
                execution = execute_project_setup(
                    prepared,
                    confirmed_setup_id=prepared.setup_id,
                )
            self.assertEqual(execution.outcome, ProjectSetupOutcome.STOPPED_SAFELY)

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

    def test_inspect_existing_wordlist_oserror(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            with patch(
                "spell_sync.io.read_text_words",
                side_effect=OSError("permission denied"),
            ):
                count, status, detail = inspect_existing_wordlist(wordlist)
            self.assertIsNone(count)
            self.assertEqual(detail, "permission denied")

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

    def test_safe_discard_snapshot_resolve_oserror(self):
        from spell_sync.push_journal import DiscardSafetyError, _safe_txn_snapshot_dir

        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal = write_test_journal(
                wordlist,
                state=JOURNAL_STATE_COMPLETED,
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            snapshot_dir = journal.snapshot_dir
            transaction_id = journal.transaction_id
            snap = Path(snapshot_dir)
            with patch("spell_sync.push_journal.txn_snapshot_root", return_value=snap):
                with patch.object(Path, "resolve", side_effect=OSError("broken")):
                    with self.assertRaises(DiscardSafetyError):
                        _safe_txn_snapshot_dir(wordlist, transaction_id, snapshot_dir)

    def test_safe_discard_snapshot_not_directory(self):
        from spell_sync.push_journal import DiscardSafetyError, _safe_txn_snapshot_dir

        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal = write_test_journal(
                wordlist,
                state=JOURNAL_STATE_COMPLETED,
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            snap = Path(journal.snapshot_dir)
            resolved = snap.resolve()
            with patch.object(type(snap), "is_symlink", return_value=False):
                with patch.object(type(snap), "resolve", return_value=resolved):
                    with patch.object(type(snap), "is_dir", return_value=False):
                        with self.assertRaises(DiscardSafetyError):
                            _safe_txn_snapshot_dir(
                                wordlist,
                                journal.transaction_id,
                                journal.snapshot_dir,
                            )

    def test_safe_discard_journal_resolves_outside_project(self):
        from spell_sync.push_journal import journal_path_for_wordlist

        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "project" / "wordlist.txt"
            wordlist.parent.mkdir(parents=True)
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal = journal_path_for_wordlist(wordlist)
            journal.write_text("{}", encoding="utf-8")
            outside = (Path(tmp) / "outside").resolve()
            real_resolve = Path.resolve

            def selective_resolve(self: Path) -> Path:
                if self == journal:
                    return outside
                return real_resolve(self)

            with patch.object(Path, "resolve", selective_resolve):
                ok, detail = safe_discard_journal_file(wordlist)
            self.assertFalse(ok)
            self.assertIn("outside project", detail or "")


class TestPhase2BCliCoverage(unittest.TestCase):
    def test_review_removals_for_preview_and_list(self):
        from spell_sync.application.reports import PushPreview, TargetPreview
        from spell_sync.removal_review import (
            list_removals_from_preview,
            review_removals_for_preview,
        )

        preview = PushPreview(
            prepared=MagicMock(),
            targets=(
                TargetPreview(
                    name="a",
                    additions=0,
                    removals=2,
                    status="update",
                    removal_words=frozenset({"gone", "lost"}),
                ),
            ),
            additions=0,
            removals=2,
            warnings=(),
            created_at="t",
            plan_identifier="p",
            targets_to_update=1,
            unchanged=0,
            skipped=(),
            corrupt=(),
            blocked=(),
        )
        self.assertTrue(review_removals_for_preview(preview, interactive=False))
        diffs = list_removals_from_preview(preview)
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0].to_remove, 2)
        with (
            patch("builtins.input", return_value="y"),
            patch("sys.stdin.isatty", return_value=True),
        ):
            self.assertTrue(review_removals_for_preview(preview, interactive=True))
        with (
            patch("builtins.input", side_effect=EOFError),
            patch("sys.stdin.isatty", return_value=True),
        ):
            self.assertIsNone(review_removals_for_preview(preview, interactive=True))

        empty_removals = PushPreview(
            prepared=MagicMock(),
            targets=(TargetPreview(name="a", additions=1, removals=0, status="add"),),
            additions=1,
            removals=0,
            warnings=(),
            created_at="t",
            plan_identifier="p",
            targets_to_update=1,
            unchanged=0,
            skipped=(),
            corrupt=(),
            blocked=(),
        )
        self.assertTrue(review_removals_for_preview(empty_removals, interactive=False))
        mixed_preview = PushPreview(
            prepared=MagicMock(),
            targets=(
                TargetPreview(name="a", additions=1, removals=0, status="add"),
                TargetPreview(
                    name="b",
                    additions=0,
                    removals=1,
                    status="update",
                    removal_words=frozenset({"x"}),
                ),
            ),
            additions=1,
            removals=1,
            warnings=(),
            created_at="t",
            plan_identifier="p",
            targets_to_update=1,
            unchanged=0,
            skipped=(),
            corrupt=(),
            blocked=(),
        )
        mixed = list_removals_from_preview(mixed_preview)
        self.assertEqual(len(mixed), 1)

    def test_confirm_push_removals_for_preview(self):
        import spell_sync.command_helpers as command_helpers
        from spell_sync.application.reports import PushPreview
        from spell_sync.runtime_settings import RuntimeSettings

        prepared = MagicMock()
        prepared.max_removals.return_value = 100
        prepared.ctx.settings = RuntimeSettings.from_config_dict(
            {"push": {"max_removals_without_confirm": 50}}
        )
        preview = PushPreview(
            prepared=prepared,
            targets=(),
            additions=0,
            removals=100,
            warnings=(),
            created_at="t",
            plan_identifier="p",
            targets_to_update=0,
            unchanged=0,
            skipped=(),
            corrupt=(),
            blocked=(),
        )
        limit_patch = "spell_sync.command_helpers.push_max_removals_without_confirm"
        opts = CliOptions()
        with patch(limit_patch, return_value=50), patch("sys.stdin.isatty", return_value=False):
            self.assertFalse(command_helpers.confirm_push_removals_for_preview(preview, opts))
        self.assertTrue(
            command_helpers.confirm_push_removals_for_preview(preview, CliOptions(dry_run=True)),
        )
        with (
            patch(limit_patch, return_value=50),
            patch("sys.stdin.isatty", return_value=True),
            patch("builtins.input", return_value="y"),
        ):
            self.assertTrue(command_helpers.confirm_push_removals_for_preview(preview, opts))
        with (
            patch(limit_patch, return_value=50),
            patch("sys.stdin.isatty", return_value=True),
            patch("builtins.input", side_effect=EOFError),
        ):
            self.assertIsNone(command_helpers.confirm_push_removals_for_preview(preview, opts))

    def test_plan_cmd_removals_and_wordlist_error(self):
        from service_test_utils import patch_plan_service

        import spell_sync.plan_cmd as plan_mod
        from spell_sync.application.reports import PushPreview, TargetPreview

        preview = PushPreview(
            prepared=MagicMock(),
            targets=(
                TargetPreview(
                    name="a",
                    additions=0,
                    removals=1,
                    status="update",
                    removal_words=frozenset({"x"}),
                ),
            ),
            additions=0,
            removals=1,
            warnings=(),
            created_at="t",
            plan_identifier="p",
            targets_to_update=1,
            unchanged=0,
            skipped=(),
            corrupt=(),
            blocked=(),
        )
        with patch_plan_service(load_push_preview=preview):
            code = plan_mod.cmd_plan(CliOptions(plan_removals=True))
        self.assertEqual(code, int(ExitCode.OK))

        bad = PushPreview(
            prepared=None,
            targets=(),
            additions=0,
            removals=0,
            warnings=(),
            created_at="t",
            plan_identifier="u",
            targets_to_update=0,
            unchanged=0,
            skipped=(),
            corrupt=(),
            blocked=(),
            wordlist_error=ExitCode.WORDLIST_UNREADABLE,
        )
        with patch_plan_service(load_push_preview=bad):
            code = plan_mod.cmd_plan(CliOptions(plan_removals=True, json_output=True))
        self.assertEqual(code, int(ExitCode.WORDLIST_UNREADABLE))

        blocked_plan = (
            bad,
            (),
            ExitCode.PUSH_ABORT,
        )
        with patch_plan_service(load_push_plan=blocked_plan):
            code = plan_mod.cmd_plan(CliOptions(json_output=True))
        self.assertEqual(code, int(ExitCode.WORDLIST_UNREADABLE))

    def test_cmd_pull_execution_exit_code(self):
        from service_test_utils import (
            patch_commands_service,
            pull_execution,
            pull_preview_executable,
        )

        import spell_sync.commands as commands_mod

        preview = pull_preview_executable("/tmp/w.txt", 1, 1)
        execution = pull_execution(1, 1, preview=preview, result=ExitCode.PUSH_ABORT)
        with patch_commands_service(prepare_pull=preview, execute_pull=execution):
            code = commands_mod.cmd_pull(CliOptions(json_output=True))
        self.assertEqual(code, int(ExitCode.PUSH_ABORT))

    def test_recover_cmd_remaining_paths(self):
        from service_test_utils import (
            patch_recover_service,
            recoverable_preview,
            recovery_execution,
        )

        import spell_sync.recover_cmd as recover_mod
        from spell_sync.application.reports import RecoveryExecution, RecoveryOutcome

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            preview = replace(
                recoverable_preview(str(wordlist)),
                can_recover=False,
                status=RecoveryStatus.CONFLICTED,
                detail="not recoverable",
            )
            with patch_recover_service(inspect_recovery=preview):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = recover_mod.cmd_recover(
                        CliOptions(wordlist=str(wordlist), json_output=True),
                    )
                self.assertEqual(code, int(ExitCode.PUSH_ABORT))
                payload = json.loads(buf.getvalue())
                self.assertEqual(payload["reason"], RecoveryStatus.CONFLICTED.value)

            preview_ok = recoverable_preview(str(wordlist))
            with (
                patch_recover_service(inspect_recovery=preview_ok),
                patch("sys.stdin.isatty", return_value=False),
            ):
                code = recover_mod.cmd_recover(CliOptions(wordlist=str(wordlist)))
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))

            execution = RecoveryExecution(
                preview=preview_ok,
                result=0,
                outcome=RecoveryOutcome.RECOVERED,
                message="",
            )
            with patch_recover_service(
                inspect_recovery=preview_ok,
                execute_recovery=execution,
            ):
                code = recover_mod.cmd_recover(CliOptions(wordlist=str(wordlist), yes=True))
            self.assertEqual(code, int(ExitCode.OK))

            execution_ok = recovery_execution(RecoverResult((), (), ()), preview=preview_ok)
            with patch_recover_service(
                inspect_recovery=preview_ok,
                execute_recovery=execution_ok,
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = recover_mod.cmd_recover(
                        CliOptions(wordlist=str(wordlist), yes=True, json_output=True),
                    )
                self.assertEqual(code, int(ExitCode.OK))
                self.assertEqual(json.loads(buf.getvalue()).get("journal"), {})

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
        self.assertFalse(
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
