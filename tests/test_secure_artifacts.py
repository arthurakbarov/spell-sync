"""Coverage and behavior tests for spell_sync.secure_artifacts."""

from __future__ import annotations

import errno
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spell_sync.project import ProjectContext
from spell_sync.secure_artifacts import (
    SecureArtifactError,
    _fsync_directory,
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
            except (OSError, AttributeError):
                self.skipTest("mkfifo unavailable")
            with self.assertRaises(SecureArtifactError):
                open_trusted_regular_file(fifo, root=root, create=False)


if __name__ == "__main__":
    unittest.main()
