"""Mandatory adversarial regressions for descriptor-relative secure artifacts (R1–R7)."""

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from spell_sync.operation_lock import (
    OperationLockRejected,
    acquire_operation_lock,
    read_active_operation_lock,
)
from spell_sync.push_journal import JournalLoadStatus, load_journal_result
from spell_sync.secure_artifacts import (
    SecureArtifactError,
    copy_trusted_snapshot_file,
    open_trusted_regular_file,
    prepare_trusted_txn_root,
    remove_trusted_tree,
    set_open_boundary_hook,
    trusted_project_root,
)
from spell_sync.trusted_internal_fs import TrustedFsError


class TestAdversarialRegressions(unittest.TestCase):
    def _wordlist(self, root: Path) -> Path:
        wordlist = root / "wordlist.txt"
        wordlist.write_text("alpha\n", encoding="utf-8")
        return wordlist

    def test_r1_intermediate_symlink_inside_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = self._wordlist(root)
            project = trusted_project_root(wordlist)
            redirect = project / "redirect"
            redirect.mkdir(parents=True)
            txn_link = project / ".spell-sync.txn"
            txn_link.parent.mkdir(parents=True, exist_ok=True)
            txn_link.symlink_to(redirect, target_is_directory=True)
            with self.assertRaises((SecureArtifactError, TrustedFsError, OSError)):
                prepare_trusted_txn_root(wordlist, "tid")
            self.assertFalse((redirect / "tid").exists())

    def test_r2_parent_swap_before_final_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = self._wordlist(root)
            project = trusted_project_root(wordlist)
            external = root / "external"
            external.mkdir()
            safe = project / "safe"
            safe.mkdir(parents=True)
            artifact = safe / "artifact"

            def hook(phase: str, name: str) -> None:
                if phase == "before_file_open" and name == "artifact":
                    real = safe
                    backup = project / "safe.bak"
                    real.rename(backup)
                    safe.symlink_to(external)

            set_open_boundary_hook(hook)
            try:
                with self.assertRaises((SecureArtifactError, TrustedFsError)):
                    open_trusted_regular_file(
                        artifact,
                        root=project,
                        create=True,
                    )
            finally:
                set_open_boundary_hook(None)
            self.assertFalse((external / "artifact").exists())

    def test_r3_snapshot_path_swap_victim_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = self._wordlist(root)
            project = trusted_project_root(wordlist)
            victim = project / "victim.txt"
            victim.write_text("secret\n", encoding="utf-8")
            source = project / "source.txt"
            source.write_text("payload\n", encoding="utf-8")
            txn_dir = prepare_trusted_txn_root(wordlist, "tid")
            snap_name_holder: list[str] = []

            def hook(phase: str, name: str) -> None:
                if phase != "before_snapshot_copy":
                    return
                snap_name_holder.append(name)
                snap_path = txn_dir / name
                if snap_path.exists() or snap_path.is_symlink():
                    snap_path.unlink()
                snap_path.symlink_to(victim)

            set_open_boundary_hook(hook)
            try:
                copy_trusted_snapshot_file(
                    txn_dir,
                    root=project,
                    base_name="dict",
                    source=source,
                )
            finally:
                set_open_boundary_hook(None)
            self.assertTrue(snap_name_holder)
            self.assertEqual(victim.read_text(encoding="utf-8"), "secret\n")

    def test_r4_cleanup_directory_swap_preserves_unrelated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = self._wordlist(root)
            project = trusted_project_root(wordlist)
            unrelated = project / "unrelated"
            unrelated.mkdir(parents=True)
            keep = unrelated / "keep.txt"
            keep.write_text("stay\n", encoding="utf-8")
            txn_dir = prepare_trusted_txn_root(wordlist, "tid")
            snap = txn_dir / "snap.txt"
            snap.write_text("snap\n", encoding="utf-8")

            def hook(phase: str, _name: str) -> None:
                if phase != "before_cleanup_listdir":
                    return
                txn_parent = project / ".spell-sync.txn"
                backup = project / ".spell-sync.txn.bak"
                txn_parent.rename(backup)
                txn_parent.symlink_to(unrelated, target_is_directory=True)

            set_open_boundary_hook(hook)
            try:
                remove_trusted_tree(txn_dir, root=project)
            finally:
                set_open_boundary_hook(None)
            self.assertTrue(keep.exists())
            self.assertEqual(keep.read_text(encoding="utf-8"), "stay\n")

    def test_r5_unsafe_internal_reads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = self._wordlist(root)
            project = trusted_project_root(wordlist)
            external_journal = root / "external-journal.json"
            external_journal.write_text('{"pid": 1}\n', encoding="utf-8")
            external_lock = root / "external-lock.json"
            external_lock.write_text('{"pid": 1}\n', encoding="utf-8")
            journal = project / ".spell-sync.journal.json"
            journal.parent.mkdir(parents=True, exist_ok=True)
            journal.symlink_to(external_journal)
            lock_path = project / ".spell-sync.lock"
            lock_path.symlink_to(external_lock)
            result = load_journal_result(wordlist)
            self.assertEqual(result.status, JournalLoadStatus.UNSAFE_ARTIFACT)
            with self.assertRaises(OperationLockRejected):
                with acquire_operation_lock(wordlist, "push"):
                    pass
            self.assertIsNone(read_active_operation_lock(wordlist))

    def test_r6_lock_hard_link_victim_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = self._wordlist(root)
            project = trusted_project_root(wordlist)
            victim = project / "victim.txt"
            victim.write_text("secret\n", encoding="utf-8")
            lock_path = project / ".spell-sync.lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            os.link(victim, lock_path)
            with self.assertRaises(OperationLockRejected):
                with acquire_operation_lock(wordlist, "push"):
                    pass
            self.assertEqual(victim.read_text(encoding="utf-8"), "secret\n")

    def test_r7_existing_insecure_transaction_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = self._wordlist(root)
            project = trusted_project_root(wordlist)
            txn_parent = project / ".spell-sync.txn"
            txn_parent.mkdir(parents=True)
            os.chmod(txn_parent, 0o777)
            prepare_trusted_txn_root(wordlist, "tid")
            mode = stat.S_IMODE(os.stat(txn_parent).st_mode)
            self.assertEqual(mode, 0o700)


if __name__ == "__main__":
    unittest.main()
