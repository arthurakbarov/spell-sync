"""Coverage and behavior tests for spell_sync.secure_artifacts."""

from __future__ import annotations

import errno
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spell_sync.secure_artifacts import (
    SecureArtifactError,
    _chmod_private_dir,
    _fchmod_private,
    _fsync_directory,
    _fsync_fd,
    atomic_write_trusted_file,
    create_trusted_snapshot_file,
    ensure_trusted_directory,
    is_reparse_point,
    open_trusted_regular_file,
    prepare_trusted_txn_root,
    remove_trusted_file,
    remove_trusted_tree,
    trusted_project_root,
    trusted_project_root_resolved,
)


class TestSecureArtifactsCoverage(unittest.TestCase):
    def _project(self, tmp: str) -> tuple[Path, Path]:
        wordlist = Path(tmp) / "wordlist.txt"
        wordlist.write_text("alpha\n", encoding="utf-8")
        root = trusted_project_root(wordlist)
        return wordlist, root

    def test_trusted_root_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._project(tmp)
            self.assertEqual(trusted_project_root_resolved(wordlist), root.resolve())

    def test_ensure_and_open_and_atomic_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._project(tmp)
            target = root / ".spell-sync.journal.json"
            atomic_write_trusted_file(target, b"{}\n", root=root)
            self.assertTrue(target.is_file())
            fd = open_trusted_regular_file(target, root=root)
            os.close(fd)

    def test_atomic_write_rejects_symlink_final(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._project(tmp)
            victim = root / "victim.json"
            victim.write_text("{}\n", encoding="utf-8")
            target = root / ".spell-sync.journal.json"
            target.symlink_to(victim)
            with self.assertRaises(SecureArtifactError):
                atomic_write_trusted_file(target, b"x", root=root)

    def test_open_rejects_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._project(tmp)
            dir_path = root / ".spell-sync.txn"
            ensure_trusted_directory(dir_path, root=root)
            with self.assertRaises(SecureArtifactError):
                open_trusted_regular_file(dir_path, root=root)

    def test_remove_trusted_file_and_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._project(tmp)
            txn = prepare_trusted_txn_root(wordlist, "tid")
            snap = create_trusted_snapshot_file(txn, root=root, base_name="dict")
            snap.write_bytes(b"snap")
            remove_trusted_file(snap, root=root)
            self.assertFalse(snap.exists())
            child = txn / "nested"
            ensure_trusted_directory(child, root=root)
            (child / "f").write_text("x", encoding="utf-8")
            remove_trusted_tree(txn, root=root)
            self.assertFalse(txn.exists())

    def test_remove_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._project(tmp)
            victim = root / "victim.txt"
            victim.write_text("x", encoding="utf-8")
            link = root / "link.txt"
            link.symlink_to(victim)
            with self.assertRaises(SecureArtifactError):
                remove_trusted_file(link, root=root)

    def test_outside_root_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._project(tmp)
            outside_root = Path(tmp).parent / "outside-root" / "outside.txt"
            outside_root.parent.mkdir(parents=True, exist_ok=True)
            outside_root.write_text("x", encoding="utf-8")
            with self.assertRaises(SecureArtifactError):
                remove_trusted_file(outside_root, root=root)

    def test_prepare_txn_root_rejects_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._project(tmp)
            bad = root / ".spell-sync.txn" / "tid"
            bad.parent.mkdir(parents=True, exist_ok=True)
            bad.write_text("x", encoding="utf-8")
            with self.assertRaises(SecureArtifactError):
                prepare_trusted_txn_root(wordlist, "tid")

    def test_atomic_write_partial_write_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._project(tmp)
            target = root / ".spell-sync.journal.json"
            with patch("spell_sync.secure_artifacts.os.write", return_value=0):
                with self.assertRaises(SecureArtifactError):
                    atomic_write_trusted_file(target, b"abc", root=root)

    def test_fsync_directory_enosys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._project(tmp)
            with patch(
                "spell_sync.secure_artifacts.os.open",
                side_effect=OSError(errno.ENOSYS, "nosys"),
            ):
                _fsync_directory(root)

    def test_is_reparse_point_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / "link"
            target = Path(tmp) / "target.txt"
            target.write_text("x", encoding="utf-8")
            link.symlink_to(target)
            self.assertTrue(is_reparse_point(link))

    def test_unexpected_component_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._project(tmp)
            fifo = root / "fifo"
            try:
                os.mkfifo(fifo)
            except OSError, AttributeError:
                self.skipTest("mkfifo unavailable")
            with self.assertRaises(SecureArtifactError):
                open_trusted_regular_file(fifo, root=root, create=False)

    def test_secure_artifact_error_str(self) -> None:
        err = SecureArtifactError("code", "detail message")
        self.assertEqual(str(err), "detail message")

    def test_trusted_root_resolve_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._project(tmp)
            with patch(
                "spell_sync.secure_artifacts.trusted_project_root",
                return_value=root,
            ):
                with patch.object(Path, "resolve", side_effect=OSError("resolve failed")):
                    with self.assertRaises(SecureArtifactError):
                        trusted_project_root_resolved(wordlist)

    def test_is_reparse_point_oserror(self) -> None:
        path = Path("/definitely-not-there-xyz")
        with patch.object(Path, "is_symlink", side_effect=OSError("lstat failed")):
            self.assertFalse(is_reparse_point(path))

    def test_ensure_directory_rejects_file_component(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._project(tmp)
            blocker = root / "blocker"
            blocker.write_text("x", encoding="utf-8")
            nested = root / "blocker" / "nested"
            with self.assertRaises(SecureArtifactError):
                ensure_trusted_directory(nested, root=root)

    def test_ensure_directory_eexist_race(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._project(tmp)
            target = root / "nested" / "dir"
            real_mkdir = os.mkdir

            def mkdir_race(path, mode=0o700, *, dir_fd=None):
                if dir_fd is None:
                    real_mkdir(path, mode)
                else:
                    real_mkdir(path, mode, dir_fd=dir_fd)
                raise OSError(errno.EEXIST, "exists")

            with patch("spell_sync.trusted_internal_fs.os.mkdir", side_effect=mkdir_race):
                ensure_trusted_directory(target, root=root)
            self.assertTrue(target.is_dir())

    def test_open_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._project(tmp)
            missing = root / "missing.lock"
            with self.assertRaises(SecureArtifactError) as ctx:
                open_trusted_regular_file(missing, root=root, create=False)
            self.assertEqual(ctx.exception.code, "missing_file")

    def test_open_failure_and_fstat_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._project(tmp)
            target = root / ".spell-sync.lock"
            with patch(
                "spell_sync.secure_artifacts.os.open", side_effect=OSError(errno.EACCES, "denied")
            ):
                with self.assertRaises(SecureArtifactError) as ctx:
                    open_trusted_regular_file(target, root=root, create=True)
                self.assertEqual(ctx.exception.code, "open_failed")
            target.write_text("x", encoding="utf-8")
            with patch("spell_sync.trusted_internal_fs.os.open", return_value=99):
                with patch(
                    "spell_sync.trusted_internal_fs.os.fstat",
                    side_effect=OSError(errno.EIO, "io"),
                ):
                    with patch("spell_sync.trusted_internal_fs.os.close") as close_mock:
                        with self.assertRaises(SecureArtifactError) as ctx:
                            open_trusted_regular_file(target, root=root)
                        self.assertEqual(ctx.exception.code, "fstat_failed")
                        close_mock.assert_any_call(99)

    def test_open_rejects_non_regular_fstat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._project(tmp)
            target = root / ".spell-sync.lock"
            target.write_text("x", encoding="utf-8")
            with patch("spell_sync.trusted_internal_fs.os.open", return_value=99):
                with patch(
                    "spell_sync.trusted_internal_fs.os.fstat",
                    return_value=type("ST", (), {"st_mode": 0o040000})(),
                ):
                    with patch("spell_sync.trusted_internal_fs.os.close") as close_mock:
                        with self.assertRaises(SecureArtifactError) as ctx:
                            open_trusted_regular_file(target, root=root)
                        self.assertEqual(ctx.exception.code, "not_a_file")
                        close_mock.assert_any_call(99)

    def test_fchmod_and_chmod_private_swallow_oserror(self) -> None:
        with patch(
            "spell_sync.secure_artifacts.os.fchmod", side_effect=OSError(errno.EPERM, "perm")
        ):
            _fchmod_private(1)
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "spell_sync.secure_artifacts.os.chmod", side_effect=OSError(errno.EPERM, "perm")
            ):
                _chmod_private_dir(Path(tmp))

    def test_fsync_fd_raises_non_enosys(self) -> None:
        with patch("spell_sync.secure_artifacts.os.fsync", side_effect=OSError(errno.EIO, "io")):
            with self.assertRaises(OSError):
                _fsync_fd(1)

    def test_fsync_directory_open_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "spell_sync.secure_artifacts.os.open",
                side_effect=OSError(errno.EACCES, "denied"),
            ):
                with self.assertRaises(OSError):
                    _fsync_directory(Path(tmp))

    def test_atomic_write_replace_failure_cleans_temp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._project(tmp)
            target = root / ".spell-sync.journal.json"
            with patch(
                "spell_sync.secure_artifacts.os.replace", side_effect=OSError(errno.EIO, "io")
            ):
                with self.assertRaises(SecureArtifactError) as ctx:
                    atomic_write_trusted_file(target, b"{}\n", root=root)
                self.assertEqual(ctx.exception.code, "publish_failed")
            temps = list(root.glob(".spell-sync.journal.json.*.tmp"))
            self.assertEqual(temps, [])

    def test_atomic_write_chmod_failure_still_publishes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._project(tmp)
            target = root / ".spell-sync.journal.json"
            with patch(
                "spell_sync.secure_artifacts.os.chmod", side_effect=OSError(errno.EPERM, "perm")
            ):
                atomic_write_trusted_file(target, b"{}\n", root=root)
            self.assertTrue(target.is_file())

    def test_remove_missing_file_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._project(tmp)
            missing = root / "missing.txt"
            remove_trusted_file(missing, root=root)

    def test_remove_rejects_non_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._project(tmp)
            dir_path = root / "dir"
            ensure_trusted_directory(dir_path, root=root)
            with self.assertRaises(SecureArtifactError):
                remove_trusted_file(dir_path, root=root)

    def test_remove_tree_rejects_symlink_child(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._project(tmp)
            txn = root / "tree"
            ensure_trusted_directory(txn, root=root)
            victim = root / "victim.txt"
            victim.write_text("x", encoding="utf-8")
            (txn / "link").symlink_to(victim)
            with self.assertRaises(SecureArtifactError):
                remove_trusted_tree(txn, root=root)

    def test_remove_tree_rejects_symlink_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._project(tmp)
            victim = root / "victim"
            ensure_trusted_directory(victim, root=root)
            link = root / "link"
            link.symlink_to(victim)
            with self.assertRaises(SecureArtifactError):
                remove_trusted_tree(link, root=root)

    def test_prepare_txn_root_existing_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._project(tmp)
            txn_dir = prepare_trusted_txn_root(wordlist, "existing")
            self.assertTrue(txn_dir.is_dir())
            again = prepare_trusted_txn_root(wordlist, "existing")
            self.assertEqual(again, txn_dir)

    def test_create_snapshot_chmod_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, root = self._project(tmp)
            txn = prepare_trusted_txn_root(wordlist, "snap")
            with patch(
                "spell_sync.secure_artifacts.os.chmod", side_effect=OSError(errno.EPERM, "perm")
            ):
                snap = create_trusted_snapshot_file(txn, root=root, base_name="dict")
            self.assertTrue(snap.is_file())


if __name__ == "__main__":
    unittest.main()
