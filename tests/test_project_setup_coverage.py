"""Additional coverage for project setup and related paths."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from spell_sync.application import SpellSyncService
from spell_sync.application.events import OperationEvent, OperationKind
from spell_sync.bundled_files import init_project_directory
from spell_sync.cli_options import CliOptions
from spell_sync.commands import cmd_init
from spell_sync.project_setup.draft import SetupDraft
from spell_sync.project_setup.execute import (
    ProjectSetupOutcome,
    execute_project_setup,
)
from spell_sync.project_setup.prepare import prepare_project_setup
from spell_sync.push_journal import (
    DiscardSafetyError,
    discard_journal,
    safe_discard_journal_file,
    safe_discard_txn_snapshots,
)
from spell_sync.settings import ConfigLoadResult, ConfigStatus


class TestProjectSetupCoverage(unittest.TestCase):
    def test_init_project_directory_creates_files(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            created = init_project_directory(root)
            self.assertTrue(created)
            self.assertTrue((root / "wordlist.txt").is_file())
            self.assertEqual(init_project_directory(root), [])

    def test_cmd_init_existing_project_is_noop(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project_directory(root)
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
            events: list[OperationEvent] = []

            def sink(event: OperationEvent) -> None:
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

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            wordlist = project / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal = project / ".spell-sync.journal.json"
            journal.write_text('{"schema_version":2}\n', encoding="utf-8")
            with patch.object(Path, "unlink", side_effect=OSError("nope")):
                with self.assertRaises(DiscardSafetyError):
                    discard_journal(wordlist)


if __name__ == "__main__":
    unittest.main()
