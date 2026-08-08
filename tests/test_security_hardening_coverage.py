"""Coverage for security hardening integration paths."""

from __future__ import annotations

import errno
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

from spell_sync.mutation_guards import operation_lock_scope_for
from spell_sync.operation_lock import OperationLockRejected, acquire_operation_lock
from spell_sync.push_abort import PushAbort, _combined_reason, handle_failed_push_rollback
from spell_sync.push_journal import (
    JOURNAL_STATE_WRITING,
    PushJournal,
    PushJournalSession,
    _atomic_write_journal,
    journal_path_for_wordlist,
)
from spell_sync.push_prepared import _abort_journal_begin_failure
from spell_sync.push_transaction import (
    PushTransaction,
    RollbackResult,
    TargetWriteState,
    _artifact_root,
    _FileBackup,
    backup_file,
    discard_txn_snapshots,
    rollback_backups,
)
from spell_sync.secure_artifacts import (
    SecureArtifactError,
    _chmod_private_dir,
    _flush_file_windows,
    _fsync_directory,
    _fsync_fd,
    _reject_unsafe_component,
    _relative_under_root,
    atomic_write_trusted_file,
    ensure_trusted_directory,
    is_reparse_point,
    remove_trusted_file,
    remove_trusted_tree,
    trusted_project_root,
)


class TestPushAbortPrecedence(unittest.TestCase):
    def test_combined_reason_branches(self) -> None:
        self.assertEqual(_combined_reason(), "push_aborted")
        self.assertEqual(_combined_reason("only"), "only")
        self.assertEqual(
            _combined_reason("dict_fail", "journal_update_failed", "rollback_incomplete"),
            "journal_update_failed_and_rollback_incomplete",
        )
        self.assertEqual(
            _combined_reason("dict_fail", "rollback_incomplete"), "rollback_incomplete"
        )
        self.assertEqual(_combined_reason("dict_fail", "other"), "dict_fail")

    def test_complete_rollback_journal_update_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            dict_path = root / "dict.txt"
            dict_path.write_text("b\n", encoding="utf-8")
            tx = PushTransaction(
                dictionary_backups=[
                    _FileBackup(
                        dict_path, None, True, "d", write_state=TargetWriteState.NOT_STARTED
                    )
                ],
                wordlist_backup=_FileBackup(wordlist, None, True, "wordlist"),
                transaction_id="tid",
                snapshot_dir=None,
                wordlist_path=wordlist,
            )
            session = PushJournalSession.__new__(PushJournalSession)
            session._path = journal_path_for_wordlist(wordlist)
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
                snapshot_dir=None,
                targets=[],
            )
            with patch.object(PushTransaction, "rollback", return_value=RollbackResult((), (), ())):
                with patch.object(
                    PushJournalSession, "discard", side_effect=OSError("discard fail")
                ):
                    result = handle_failed_push_rollback(
                        tx,
                        session,
                        reason="dictionary_write_failed",
                        message="push aborted",
                        journal_update_failed=True,
                    )
            self.assertEqual(result.reason, "journal_update_failed")

    def test_incomplete_rollback_mark_incomplete_oserror(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            dict_path = root / "dict.txt"
            dict_path.write_text("b\n", encoding="utf-8")
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
            session = PushJournalSession.__new__(PushJournalSession)
            session._path = journal_path_for_wordlist(wordlist)
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
            with patch.object(
                PushTransaction,
                "rollback",
                return_value=RollbackResult((), ("d",), ()),
            ):
                with patch.object(
                    PushJournalSession,
                    "mark_rollback_incomplete",
                    side_effect=OSError("mark fail"),
                ):
                    result = handle_failed_push_rollback(
                        tx,
                        session,
                        reason="dictionary_write_failed",
                        message="push aborted",
                        journal_update_failed=False,
                    )
            self.assertTrue(result.recovery_materials_preserved)
            self.assertEqual(result.reason, "rollback_incomplete")


class TestJournalBeginFailure(unittest.TestCase):
    def test_abort_journal_begin_cleanup_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            snap = trusted_project_root(wordlist) / ".spell-sync.txn" / "tid"
            snap.mkdir(parents=True)
            tx = PushTransaction(
                dictionary_backups=[],
                wordlist_backup=_FileBackup(wordlist, None, True, "wordlist"),
                transaction_id="tid",
                snapshot_dir=snap,
                wordlist_path=wordlist,
            )
            result = _abort_journal_begin_failure(tx, OSError("journal fail"))
            self.assertIsInstance(result, PushAbort)
            self.assertFalse(result.recovery_materials_preserved)
            self.assertIsNone(tx.snapshot_dir)

    def test_abort_journal_begin_cleanup_partial(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            snap = trusted_project_root(wordlist) / ".spell-sync.txn" / "tid"
            snap.mkdir(parents=True)
            tx = PushTransaction(
                dictionary_backups=[],
                wordlist_backup=_FileBackup(wordlist, None, True, "wordlist"),
                transaction_id="tid",
                snapshot_dir=snap,
                wordlist_path=wordlist,
            )
            with patch(
                "spell_sync.push_prepared.safe_discard_txn_snapshots",
                return_value=(False, "leftover"),
            ):
                result = _abort_journal_begin_failure(tx, OSError("journal fail"))
            self.assertTrue(result.recovery_materials_preserved)
            self.assertTrue(result.recovery_required)


class TestMutationGuardsLockRejected(unittest.TestCase):
    def test_operation_lock_context_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            lock = trusted_project_root(wordlist) / ".spell-sync.lock"
            lock.parent.mkdir(parents=True, exist_ok=True)
            lock.symlink_to(wordlist)
            with patch("spell_sync.mutation_guards.emit_json") as emit:
                with operation_lock_scope_for(wordlist, "push", json_output=True) as exit_code:
                    self.assertEqual(exit_code, 1)
                emit.assert_called_once()
                payload = emit.call_args[0][0]
                self.assertEqual(payload["reason"], "unsafe_operation_lock")

    def test_operation_lock_context_human(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            lock = trusted_project_root(wordlist) / ".spell-sync.lock"
            lock.parent.mkdir(parents=True, exist_ok=True)
            lock.symlink_to(wordlist)
            with patch("spell_sync.mutation_guards.log.abort") as abort:
                with operation_lock_scope_for(wordlist, "push", json_output=False) as exit_code:
                    self.assertEqual(exit_code, 1)
                abort.assert_called_once()


class TestOperationLockMkdirFailure(unittest.TestCase):
    def test_lock_parent_mkdir_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "nested" / "wordlist.txt"
            with patch.object(Path, "mkdir", side_effect=OSError(errno.EROFS, "ro")):
                with self.assertRaises(OperationLockRejected):
                    with acquire_operation_lock(wordlist, "push"):
                        pass


class TestPushTransactionBranches(unittest.TestCase):
    def test_artifact_root_fallback(self) -> None:
        backup_dir = Path("/tmp/backup-dir")
        self.assertEqual(_artifact_root(backup_dir, None), backup_dir.parent)

    def test_rollback_restored_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dict.txt"
            path.write_text("old\n", encoding="utf-8")
            backup = Path(tmp) / "snap"
            backup.write_text("old\n", encoding="utf-8")
            bak = _FileBackup(path, backup, True, "d", write_state=TargetWriteState.WRITE_STARTED)
            result = rollback_backups([bak])
            self.assertIn("d", result.restored)

    def test_begin_rejects_unsafe_txn_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            root = trusted_project_root(wordlist)
            bad_txn = root / ".spell-sync.txn"
            bad_txn.write_text("not-a-directory", encoding="utf-8")
            with self.assertRaises(OSError):
                PushTransaction.begin(wordlist, [])

    def test_discard_removes_empty_txn_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            root = trusted_project_root(wordlist)
            snap = root / ".spell-sync.txn" / "tid"
            snap.mkdir(parents=True)
            (snap / "file.snap").write_text("x", encoding="utf-8")
            discard_txn_snapshots(snap, wordlist=wordlist, transaction_id="tid")
            self.assertFalse(snap.exists())
            self.assertFalse((root / ".spell-sync.txn").exists())

    def test_backup_file_uses_explicit_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            root = trusted_project_root(wordlist)
            snap = root / ".spell-sync.txn" / "tid"
            snap.mkdir(parents=True)
            bak = backup_file(wordlist, snap, root=root)
            self.assertTrue(bak.existed_before)


class TestSecureArtifactsRemainingCoverage(unittest.TestCase):
    def test_reject_unsafe_nonexistent(self) -> None:
        assert _reject_unsafe_component(Path("/nonexistent-path-xyz")) is None

    def test_is_reparse_point_windows_attrs(self) -> None:
        with patch.object(sys, "platform", "win32"):
            path = Path("fake")
            with patch.object(Path, "is_symlink", return_value=False):
                with patch.object(Path, "lstat") as lstat:
                    lstat.return_value = type(
                        "ST",
                        (),
                        {"st_file_attributes": 0x400},
                    )()
                    self.assertTrue(is_reparse_point(path))

    def test_ensure_directory_eexist_not_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            root = trusted_project_root(wordlist)
            blocker = root / "blocker"
            blocker.write_text("x", encoding="utf-8")
            with self.assertRaises(SecureArtifactError):
                ensure_trusted_directory(root / "blocker" / "nested", root=root)

    def test_atomic_write_temp_fd_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            root = trusted_project_root(wordlist)
            target = root / ".spell-sync.journal.json"
            with patch(
                "spell_sync.trusted_internal_fs.os.write", side_effect=OSError(errno.EIO, "io")
            ):
                with self.assertRaises(SecureArtifactError):
                    atomic_write_trusted_file(target, b"x", root=root)

    def test_atomic_write_temp_unlink_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            root = trusted_project_root(wordlist)
            target = root / ".spell-sync.journal.json"
            with patch(
                "spell_sync.secure_artifacts.os.replace", side_effect=OSError(errno.EIO, "io")
            ):
                with patch.object(Path, "unlink", side_effect=OSError(errno.EIO, "io")):
                    with self.assertRaises(SecureArtifactError):
                        atomic_write_trusted_file(target, b"x", root=root)

    def test_remove_file_reparse_and_non_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            root = trusted_project_root(wordlist)
            link = root / "link.txt"
            victim = root / "victim.txt"
            victim.write_text("x", encoding="utf-8")
            link.symlink_to(victim)
            with self.assertRaises(SecureArtifactError):
                remove_trusted_file(link, root=root)
            dir_path = root / "dir"
            ensure_trusted_directory(dir_path, root=root)
            with self.assertRaises(SecureArtifactError):
                remove_trusted_file(dir_path, root=root)

    def test_remove_tree_missing_and_not_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            root = trusted_project_root(wordlist)
            remove_trusted_tree(root / "missing", root=root)
            file_path = root / "file.txt"
            file_path.write_text("x", encoding="utf-8")
            with self.assertRaises(SecureArtifactError):
                remove_trusted_tree(file_path, root=root)

    def test_remove_tree_rmdir_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            root = trusted_project_root(wordlist)
            tree = root / "tree"
            ensure_trusted_directory(tree, root=root)
            with patch(
                "spell_sync.trusted_internal_fs.os.rmdir", side_effect=OSError(errno.EBUSY, "busy")
            ):
                with self.assertRaises(SecureArtifactError):
                    remove_trusted_tree(tree, root=root)

    @unittest.skipUnless(sys.platform == "win32", "Windows-only branches")
    def test_windows_private_helpers(self) -> None:
        assert _chmod_private_dir(Path(".")) is None
        assert _fsync_directory(Path(".")) is None
        assert _flush_file_windows(1) is None

    def test_windows_branches_via_platform_patch(self) -> None:
        fake_msvcrt = MagicMock()
        fake_msvcrt.get_osfhandle.return_value = 1
        fake_ctypes = MagicMock()
        with patch.object(sys, "platform", "win32"):
            _chmod_private_dir(Path("."))
            _fsync_directory(Path("."))
            with patch(
                "spell_sync.trusted_internal_fs.os.fsync", side_effect=OSError(errno.EINVAL, "bad")
            ):
                with patch.dict(
                    sys.modules,
                    {"msvcrt": fake_msvcrt, "ctypes": fake_ctypes},
                ):
                    assert _flush_file_windows(1) is None


class TestRemainingCoverageGaps(unittest.TestCase):
    def test_relative_under_root_rejects_outside(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            root = trusted_project_root(wordlist)
            outside = Path(tmp).parent / "outside" / "file.txt"
            with self.assertRaises(SecureArtifactError):
                _relative_under_root(outside, root)

    def test_reject_unsafe_component_reparse_and_unexpected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target.txt"
            target.write_text("x", encoding="utf-8")
            link = Path(tmp) / "link"
            link.symlink_to(target)
            with self.assertRaises(SecureArtifactError):
                _reject_unsafe_component(link)
            try:
                fifo = Path(tmp) / "fifo"
                os.mkfifo(fifo)
                with self.assertRaises(SecureArtifactError):
                    _reject_unsafe_component(fifo)
            except (OSError, AttributeError):
                self.skipTest("mkfifo unavailable")

    def test_fsync_fd_enosys_ignored(self) -> None:
        with patch(
            "spell_sync.secure_artifacts.os.fsync", side_effect=OSError(errno.ENOSYS, "nosys")
        ) as fsync_mock:
            _fsync_fd(1)
            fsync_mock.assert_called_once_with(1)

    def test_flush_windows_nested_oserror(self) -> None:
        fake_msvcrt = MagicMock()
        fake_msvcrt.get_osfhandle.side_effect = OSError(errno.EINVAL, "bad")
        with patch.object(sys, "platform", "win32"):
            with patch(
                "spell_sync.trusted_internal_fs.os.fsync", side_effect=OSError(errno.EINVAL, "bad")
            ):
                with patch.dict(sys.modules, {"msvcrt": fake_msvcrt}):
                    assert _flush_file_windows(1) is None
            fake_msvcrt.get_osfhandle.assert_called_once()

    def test_ensure_directory_mkdir_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            root = trusted_project_root(wordlist)
            target = root / "newdir"
            with patch(
                "spell_sync.trusted_internal_fs.os.mkdir",
                side_effect=OSError(errno.EACCES, "denied"),
            ):
                with self.assertRaises(SecureArtifactError) as ctx:
                    ensure_trusted_directory(target, root=root)
                self.assertEqual(ctx.exception.code, "mkdir_failed")

    def test_ensure_directory_eexist_not_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            root = trusted_project_root(wordlist)
            leaf = root / "leaf"
            leaf.write_text("file-not-dir", encoding="utf-8")
            with self.assertRaises(SecureArtifactError):
                ensure_trusted_directory(leaf / "child", root=root)

    def test_atomic_write_inner_close_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            root = trusted_project_root(wordlist)
            target = root / ".spell-sync.journal.json"
            with patch(
                "spell_sync.trusted_internal_fs.os.write", side_effect=OSError(errno.EIO, "write")
            ):
                with self.assertRaises(SecureArtifactError):
                    atomic_write_trusted_file(target, b"x", root=root)

    def test_remove_existing_symlink_and_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            root = trusted_project_root(wordlist)
            victim = root / "victim.txt"
            victim.write_text("x", encoding="utf-8")
            link = root / "link.txt"
            link.symlink_to(victim)
            with self.assertRaises(SecureArtifactError):
                remove_trusted_file(link, root=root)
            dir_path = root / "dir"
            ensure_trusted_directory(dir_path, root=root)
            with self.assertRaises(SecureArtifactError):
                remove_trusted_file(dir_path, root=root)

    def test_atomic_write_journal_wraps_secure_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            journal = journal_path_for_wordlist(wordlist)
            journal.parent.mkdir(parents=True, exist_ok=True)
            journal.symlink_to(wordlist)
            journal_obj = PushJournal(
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
                snapshot_dir=None,
                targets=[],
            )
            with self.assertRaises(OSError):
                _atomic_write_journal(journal, journal_obj, wordlist=wordlist)

    def test_discard_txn_snapshots_swallows_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            root = trusted_project_root(wordlist)
            snap = root / ".spell-sync.txn" / "tid"
            snap.mkdir(parents=True)
            with patch(
                "spell_sync.push_transaction.remove_trusted_tree",
                side_effect=SecureArtifactError("bad", "bad"),
            ):
                discard_txn_snapshots(snap, wordlist=wordlist, transaction_id="tid")
            self.assertTrue(snap.exists())

    def test_artifact_root_from_txn_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            root = trusted_project_root(wordlist)
            snap = root / ".spell-sync.txn" / "tid"
            snap.mkdir(parents=True)
            self.assertEqual(_artifact_root(snap, None), root)


class TestPushCliRecoveryJson(unittest.TestCase):
    def test_finish_push_json_includes_recovery_required(self) -> None:
        from spell_sync.cli_options import CliOptions
        from spell_sync.command_helpers import finish_push
        from spell_sync.exit_codes import ExitCode
        from spell_sync.json_output import reset_json_emission

        reset_json_emission()
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = finish_push(
                ExitCode.PUSH_ABORT,
                CliOptions(json_output=True),
                recovery_required=True,
                outcome="recovery_required",
            )
        self.assertEqual(code, int(ExitCode.PUSH_ABORT))
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["recovery_required"])
        self.assertEqual(payload["outcome"], "recovery_required")


if __name__ == "__main__":
    unittest.main()
