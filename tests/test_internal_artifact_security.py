"""Adversarial filesystem tests for internal spell-sync artifacts."""

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spell_sync.operation_lock import OperationLockRejected, acquire_operation_lock
from spell_sync.project import ProjectContext
from spell_sync.push_abort import PushAbort, handle_failed_push_rollback
from spell_sync.push_journal import (
    JOURNAL_STATE_WRITING,
    PushJournal,
    PushJournalSession,
    journal_path_for_wordlist,
)
from spell_sync.push_transaction import PushTransaction, TargetWriteState, _FileBackup
from spell_sync.secure_artifacts import atomic_write_trusted_file


class TestSecureArtifacts(unittest.TestCase):
    def test_lock_symlink_victim_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            victim = root / "victim.txt"
            victim.write_text("secret\n", encoding="utf-8")
            wordlist = root / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            lock_path = ProjectContext.build(wordlist).project_dir / ".spell-sync.lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_path.symlink_to(victim)
            with self.assertRaises(OperationLockRejected):
                with acquire_operation_lock(wordlist, "push"):
                    pass
            self.assertEqual(victim.read_text(encoding="utf-8"), "secret\n")

    def test_journal_final_symlink_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            victim = root / "victim.json"
            victim.write_text("{}\n", encoding="utf-8")
            wordlist = root / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal = journal_path_for_wordlist(wordlist)
            journal.parent.mkdir(parents=True, exist_ok=True)
            journal.symlink_to(victim)
            project_root = ProjectContext.build(wordlist).project_dir
            with self.assertRaises(OSError):
                atomic_write_trusted_file(
                    journal,
                    b"{}\n",
                    root=project_root,
                )
            self.assertEqual(victim.read_text(encoding="utf-8"), "{}\n")

    def test_incomplete_rollback_preserves_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal_path = journal_path_for_wordlist(wordlist)
            journal_path.write_text('{"state":"writing"}\n', encoding="utf-8")
            dict_path = root / "dict.txt"
            dict_path.write_text("beta\n", encoding="utf-8")
            tx = PushTransaction(
                dictionary_backups=[
                    _FileBackup(
                        dict_path,
                        None,
                        True,
                        "d",
                        write_state=TargetWriteState.WRITE_STARTED,
                    )
                ],
                wordlist_backup=_FileBackup(wordlist, None, True, "wordlist"),
                transaction_id="tid",
                snapshot_dir=root / ".spell-sync.txn" / "tid",
                wordlist_path=wordlist,
            )
            tx.snapshot_dir.mkdir(parents=True)
            (tx.snapshot_dir / "snap").write_text("x", encoding="utf-8")
            session = PushJournalSession.__new__(PushJournalSession)
            session._path = journal_path
            session._wordlist = wordlist
            session._journal = PushJournal(
                schema_version=2,
                transaction_id="tid",
                command="push",
                pid=os.getpid(),
                started="2026-01-01T00:00:00+00:00",
                state=JOURNAL_STATE_WRITING,
                wordlist=str(wordlist),
                wordlist_hash_before=None,
                wordlist_hash_after=None,
                wordlist_backup_path=None,
                wordlist_existed_before=True,
                snapshot_dir=str(tx.snapshot_dir),
                targets=[],
            )
            with patch.object(PushJournalSession, "_persist", lambda self: None):
                result = handle_failed_push_rollback(
                    tx,
                    session,
                    reason="dictionary_write_failed",
                    message="push aborted",
                    journal_update_failed=True,
                )
            self.assertIsInstance(result, PushAbort)
            self.assertTrue(result.recovery_materials_preserved)
            self.assertTrue(journal_path.exists())
            self.assertTrue(tx.snapshot_dir.exists())

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "POSIX nofollow required")
    def test_journal_legacy_tmp_symlink_not_followed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            victim = root / "victim.tmp"
            victim.write_text("old\n", encoding="utf-8")
            wordlist = root / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal = journal_path_for_wordlist(wordlist)
            legacy = journal.with_suffix(journal.suffix + ".tmp")
            journal.parent.mkdir(parents=True, exist_ok=True)
            legacy.symlink_to(victim)
            project_root = ProjectContext.build(wordlist).project_dir
            atomic_write_trusted_file(journal, b'{"ok":true}\n', root=project_root)
            self.assertEqual(victim.read_text(encoding="utf-8"), "old\n")
            self.assertTrue(journal.is_file())
            mode = journal.stat().st_mode
            self.assertEqual(mode & stat.S_IRWXG, 0)
            self.assertEqual(mode & stat.S_IRWXO, 0)


if __name__ == "__main__":
    unittest.main()
