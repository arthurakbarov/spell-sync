"""Real-core recovery safety tests."""

import tempfile
import unittest
from pathlib import Path

from spell_sync.application.reports import RecoveryOutcome, RecoveryStatus
from spell_sync.application.requests import (
    ProjectRef,
    RecoveryRequest,
)
from spell_sync.application.service import SpellSyncService
from spell_sync.push_journal import (
    JournalLoadStatus,
    load_journal_result,
    recover_from_journal,
)
from tests.journal_test_utils import write_restore_scenario_journal


class TestTuiRecoverySafety(unittest.TestCase):
    def test_inspect_recoverable_journal(self):
        service = SpellSyncService()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            dictionary = root / "dict.txt"
            write_restore_scenario_journal(wordlist, dictionary)
            preview = service.inspect_recovery(
                RecoveryRequest(project=ProjectRef(wordlist=wordlist))
            )
            self.assertEqual(preview.status, RecoveryStatus.RECOVERABLE)
            self.assertTrue(preview.can_recover)
            self.assertEqual(preview.recoverable_count, 2)

    def test_execute_recovery_restores_files(self):
        service = SpellSyncService()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            dictionary = root / "dict.txt"
            write_restore_scenario_journal(
                wordlist,
                dictionary,
                current_wordlist="new\n",
                backup_wordlist="old\n",
                current_dict="new\n",
                backup_dict="old\n",
            )
            preview = service.inspect_recovery(
                RecoveryRequest(project=ProjectRef(wordlist=wordlist))
            )
            execution = service.execute_recovery(
                RecoveryRequest(project=ProjectRef(wordlist=wordlist)),
                preview,
                confirmed_transaction_id=preview.preview_fingerprint,
            )
            self.assertEqual(execution.outcome, RecoveryOutcome.RECOVERED)
            self.assertIn("old", wordlist.read_text(encoding="utf-8"))
            self.assertEqual(
                load_journal_result(wordlist).status,
                JournalLoadStatus.ABSENT,
            )

    def test_external_change_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            dictionary = root / "dict.txt"
            journal = write_restore_scenario_journal(wordlist, dictionary)
            dictionary.write_text("external\n", encoding="utf-8")
            result = recover_from_journal(journal, dry_run=False)
            self.assertIn("d", result.conflicts)
            self.assertIn("external", dictionary.read_text(encoding="utf-8"))

    def test_absent_journal_preview(self):
        service = SpellSyncService()
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            preview = service.inspect_recovery(
                RecoveryRequest(project=ProjectRef(wordlist=wordlist))
            )
            self.assertEqual(preview.status, RecoveryStatus.ABSENT)
            self.assertFalse(preview.can_recover)


if __name__ == "__main__":
    unittest.main()
