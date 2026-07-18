"""Recovery discard safety regression tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from spell_sync.application.reports import RecoveryOutcome, RecoveryStatus
from spell_sync.application.service import SpellSyncService
from spell_sync.cli_options import CliOptions
from spell_sync.push_journal import (
    JOURNAL_STATE_COMPLETED,
    JournalLoadStatus,
    discard_completed_journal,
    journal_path_for_wordlist,
    load_journal_result,
)
from tests.journal_test_utils import write_restore_scenario_journal, write_test_journal


class TestRecoveryDiscardSafety(unittest.TestCase):
    def test_symlink_snapshot_dir_blocks_discard_and_preserves_external_files(self):
        service = SpellSyncService()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            wordlist = project / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            victim_dir = root / "victim"
            victim_dir.mkdir()
            victim = victim_dir / "important.txt"
            victim.write_text("keep me\n", encoding="utf-8")
            journal = write_test_journal(
                wordlist,
                state=JOURNAL_STATE_COMPLETED,
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            snap = Path(journal.snapshot_dir)
            if snap.exists():
                for child in snap.iterdir():
                    child.unlink()
                snap.rmdir()
            snap.symlink_to(victim_dir, target_is_directory=True)

            preview = service.inspect_recovery(CliOptions(wordlist=str(wordlist)))
            self.assertEqual(preview.status, RecoveryStatus.COMPLETED_CLEANUP_PENDING)
            execution = service.execute_recovery_discard(
                CliOptions(wordlist=str(wordlist)),
                preview,
                confirmed_transaction_id=preview.preview_fingerprint,
            )
            self.assertEqual(execution.outcome, RecoveryOutcome.FAILED)
            self.assertTrue(victim.read_text(encoding="utf-8").startswith("keep me"))
            self.assertEqual(
                load_journal_result(wordlist).status,
                JournalLoadStatus.VALID_COMPLETED,
            )

    def test_discard_completed_journal_reports_symlink_snapshot_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            wordlist = project / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            victim_dir = root / "outside"
            victim_dir.mkdir()
            (victim_dir / "secret.txt").write_text("secret\n", encoding="utf-8")
            journal = write_test_journal(
                wordlist,
                state=JOURNAL_STATE_COMPLETED,
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            snap = Path(journal.snapshot_dir)
            if snap.exists():
                for child in snap.iterdir():
                    child.unlink()
                snap.rmdir()
            snap.symlink_to(victim_dir, target_is_directory=True)

            result = discard_completed_journal(wordlist)
            self.assertFalse(result.ok)
            self.assertTrue((victim_dir / "secret.txt").exists())

    def test_stale_recovery_confirmation_is_rejected(self):
        service = SpellSyncService()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            dictionary = root / "dict.txt"
            write_restore_scenario_journal(wordlist, dictionary)
            preview = service.inspect_recovery(CliOptions(wordlist=str(wordlist)))
            self.assertTrue(preview.can_recover)
            journal_path = journal_path_for_wordlist(wordlist)
            raw = json.loads(journal_path.read_text(encoding="utf-8"))
            raw["transaction_id"] = "00000000-0000-4000-8000-000000000099"
            journal_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
            execution = service.execute_recovery(
                CliOptions(wordlist=str(wordlist)),
                preview,
                confirmed_transaction_id=preview.preview_fingerprint,
            )
            self.assertEqual(execution.outcome, RecoveryOutcome.FAILED)
            lowered = execution.message.lower()
            self.assertTrue(
                "changed" in lowered or "no longer" in lowered or "confirmation" in lowered,
                msg=execution.message,
            )

    def test_cleanup_does_not_modify_wordlist(self):
        service = SpellSyncService()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            original = "alpha\nbeta\n"
            wordlist.write_text(original, encoding="utf-8")
            write_test_journal(
                wordlist,
                state=JOURNAL_STATE_COMPLETED,
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            preview = service.inspect_recovery(CliOptions(wordlist=str(wordlist)))
            execution = service.execute_recovery_cleanup(
                CliOptions(wordlist=str(wordlist)),
                preview,
                confirmed_transaction_id=preview.preview_fingerprint,
            )
            self.assertEqual(execution.outcome, RecoveryOutcome.CLEANUP_COMPLETED)
            self.assertEqual(wordlist.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
