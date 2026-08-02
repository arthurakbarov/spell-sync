"""Adversarial regressions for post-recovery safe_discard helpers."""

from __future__ import annotations

import os
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from spell_sync.push_journal import (
    JOURNAL_STATE_COMPLETED,
    safe_discard_journal_file,
    safe_discard_txn_snapshots,
)
from spell_sync.secure_artifacts import (
    remove_trusted_tree,
    set_open_boundary_hook,
    trusted_project_root,
)
from tests.journal_test_utils import write_test_journal


class TestSafeDiscardAdversarial(unittest.TestCase):
    def test_discard_journal_symlink_target_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            project = trusted_project_root(wordlist)
            external = root / "external-journal.json"
            external.write_text('{"state":"completed"}\n', encoding="utf-8")
            journal = project / ".spell-sync.journal.json"
            journal.parent.mkdir(parents=True, exist_ok=True)
            journal.symlink_to(external)
            ok, _detail = safe_discard_journal_file(wordlist)
            self.assertFalse(ok)
            self.assertEqual(external.read_text(encoding="utf-8"), '{"state":"completed"}\n')

    def test_discard_journal_hard_link_removes_name_preserves_victim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            project = trusted_project_root(wordlist)
            victim = project / "victim.txt"
            victim.write_text("secret\n", encoding="utf-8")
            journal = project / ".spell-sync.journal.json"
            journal.parent.mkdir(parents=True, exist_ok=True)
            os.link(victim, journal)
            ok, detail = safe_discard_journal_file(wordlist)
            self.assertTrue(ok)
            self.assertIsNone(detail)
            self.assertFalse(journal.exists())
            self.assertEqual(victim.read_text(encoding="utf-8"), "secret\n")

    def test_discard_journal_ignores_path_resolve_spoof(self) -> None:
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

            with unittest.mock.patch.object(Path, "resolve", selective_resolve):
                ok, detail = safe_discard_journal_file(wordlist)
            self.assertTrue(ok)
            self.assertIsNone(detail)
            self.assertFalse(journal.exists())

    def test_discard_snapshots_parent_swap_preserves_unrelated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            project = trusted_project_root(wordlist)
            journal = write_test_journal(
                wordlist,
                state=JOURNAL_STATE_COMPLETED,
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            unrelated = project / "unrelated"
            unrelated.mkdir(parents=True)
            keep = unrelated / "keep.txt"
            keep.write_text("stay\n", encoding="utf-8")
            snap = Path(journal.snapshot_dir)
            (snap / "orphan.snap").write_text("x", encoding="utf-8")

            def hook(phase: str, _name: str) -> None:
                if phase != "before_cleanup_listdir":
                    return
                txn_parent = project / ".spell-sync.txn"
                backup = project / ".spell-sync.txn.bak"
                txn_parent.rename(backup)
                txn_parent.symlink_to(unrelated, target_is_directory=True)

            set_open_boundary_hook(hook)
            try:
                ok, detail = safe_discard_txn_snapshots(
                    wordlist,
                    journal.transaction_id,
                    journal.snapshot_dir,
                )
            finally:
                set_open_boundary_hook(None)
            self.assertTrue(ok)
            self.assertIsNone(detail)
            self.assertTrue(keep.exists())
            self.assertEqual(keep.read_text(encoding="utf-8"), "stay\n")

    def test_discard_snapshots_symlink_rejected(self) -> None:
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
                remove_trusted_tree(snap, root=trusted_project_root(wordlist))
            snap.parent.mkdir(parents=True, exist_ok=True)
            snap.symlink_to(outside, target_is_directory=True)
            ok, detail = safe_discard_txn_snapshots(
                wordlist,
                journal.transaction_id,
                journal.snapshot_dir,
            )
            self.assertFalse(ok)
            self.assertIn("symlink", detail or "")

    def test_discard_empty_txn_parent_via_descriptor(self) -> None:
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
            (snap / "file.snap").write_text("x", encoding="utf-8")
            ok, detail = safe_discard_txn_snapshots(
                wordlist,
                journal.transaction_id,
                journal.snapshot_dir,
            )
            self.assertTrue(ok)
            self.assertIsNone(detail)
            txn_parent = trusted_project_root(wordlist) / ".spell-sync.txn"
            self.assertFalse(txn_parent.exists())


    def test_remove_empty_nested_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            project = trusted_project_root(wordlist)
            nested = project / "nested" / "empty"
            nested.mkdir(parents=True)
            from spell_sync.secure_artifacts import remove_empty_trusted_directory

            remove_empty_trusted_directory(nested, root=project)
            self.assertFalse(nested.exists())
            self.assertTrue((project / "nested").exists())

    def test_remove_empty_non_empty_directory_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            project = trusted_project_root(wordlist)
            target = project / ".spell-sync.txn"
            target.mkdir()
            (target / "keep.txt").write_text("x", encoding="utf-8")
            from spell_sync.secure_artifacts import remove_empty_trusted_directory

            remove_empty_trusted_directory(target, root=project)
            self.assertTrue(target.exists())


if __name__ == "__main__":
    unittest.main()
