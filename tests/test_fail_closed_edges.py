"""Regression: undecodable inputs and recover/git porcelain honesty."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import write_text_words
from spell_sync.lint import load_wordlist_lines, run_lint
from spell_sync.push_journal import _plan_recovery_item
from spell_sync.push_prepared import plan_fingerprint_conflict, prepare_push
from spell_sync.settings import _parse_toml_with_issues
from spell_sync.workspace_git import inspect_workspace_git
from tests.runtime_helpers import make_sync_run


class TestUndecodableFailClosed(unittest.TestCase):
    def test_lint_load_wordlist_lines_undecodable(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wordlist.txt"
            path.write_bytes(b"ok\n" + b"x" * 70000 + b"\xff")
            self.assertIsNone(load_wordlist_lines(path))
            self.assertEqual(run_lint(str(path)), ExitCode.WORDLIST_UNREADABLE)

    def test_lint_control_characters_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wordlist.txt"
            path.write_text("alpha\x00\nbeta\n", encoding="utf-8")
            original = path.read_bytes()
            self.assertIsNone(load_wordlist_lines(path))
            self.assertEqual(run_lint(str(path)), ExitCode.WORDLIST_UNREADABLE)
            self.assertEqual(run_lint(str(path), fix=True), ExitCode.WORDLIST_UNREADABLE)
            self.assertEqual(path.read_bytes(), original)

    def test_lint_fix_aborts_when_wordlist_vanishes(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wordlist.txt"
            path.write_text("Alpha\nalpha\n", encoding="utf-8")
            with patch(
                "spell_sync.lint.load_wordlist_lines", side_effect=[["Alpha", "alpha"], None]
            ):
                self.assertEqual(run_lint(str(path), fix=True), ExitCode.WORDLIST_UNREADABLE)

    def test_config_undecodable_returns_issue(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spell-sync.toml"
            path.write_bytes(b"\xff\xfe[targets]\n")
            data, issues = _parse_toml_with_issues(path)
            self.assertEqual(data, {})
            self.assertTrue(any("undecodable" in item.lower() for item in issues))
            self.assertFalse(any(str(path) in item for item in issues))

    def test_journal_target_missing_fields_is_corrupt(self):
        import json

        from spell_sync.push_journal import (
            JournalLoadStatus,
            journal_path_for_wordlist,
            load_journal_result,
        )

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal_path = journal_path_for_wordlist(wordlist)
            journal_path.parent.mkdir(parents=True, exist_ok=True)
            journal_path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "state": "writing",
                        "command": "push",
                        "transaction_id": "00000000-0000-4000-8000-000000000001",
                        "pid": 1,
                        "started": "now",
                        "wordlist": str(wordlist),
                        "targets": [{}],
                    }
                ),
                encoding="utf-8",
            )
            result = load_journal_result(wordlist)
            self.assertEqual(result.status, JournalLoadStatus.CORRUPT)

    def test_atomic_write_preserves_existing_mode(self):
        import os
        import stat

        from spell_sync.io import atomic_write

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "dict.txt"
            path.write_text("alpha\n", encoding="utf-8")
            os.chmod(path, 0o644)
            atomic_write(path, b"beta\n")
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o644)


class TestRecoverCreatedFileNoSnapshot(unittest.TestCase):
    def test_new_file_matching_hash_after_is_ready(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "created.txt"
            target.write_text("payload\n", encoding="utf-8")
            from spell_sync.push_journal import file_content_hash

            digest = file_content_hash(target)
            plan = _plan_recovery_item(
                "demo",
                target,
                None,
                existed_before=False,
                hash_before=None,
                hash_after=digest,
                write_started=True,
                write_completed=True,
            )
            self.assertEqual(plan.status, "ready")
            self.assertEqual(plan.recovery_action, "Remove created file")


class TestWorkspaceGitUnicodePaths(unittest.TestCase):
    def test_cyrillic_project_dir_reports_dirty_wordlist(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "test"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            project = root / "слова"
            project.mkdir()
            wordlist = project / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "слова/wordlist.txt"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "init"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            wordlist.write_text("alpha\nbeta\n", encoding="utf-8")
            status = inspect_workspace_git(project)
            self.assertIsNotNone(status)
            assert status is not None
            self.assertTrue(
                any(Path(item).name == "wordlist.txt" for item in status.dirty_relpaths)
            )


class TestStaleWordlistFingerprint(unittest.TestCase):
    def test_wordlist_change_after_prepare_is_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            wordlist = root / "wordlist.txt"
            dict_path = root / "a.txt"
            write_text_words(str(wordlist), ["alpha"], "utf-8", False, quiet=True)
            write_text_words(str(dict_path), ["stale"], "utf-8", False, quiet=True)
            run = make_sync_run(
                str(wordlist),
                dictionaries=[Dictionary("a", str(dict_path), DictionaryFormat.TEXT)],
            )
            prepared = prepare_push(run.context, run.load_wordlist())
            self.assertNotIsInstance(prepared, ExitCode)
            assert not isinstance(prepared, ExitCode)
            write_text_words(str(wordlist), ["alpha", "beta"], "utf-8", False, quiet=True)
            self.assertEqual(plan_fingerprint_conflict(prepared), "wordlist.txt")


class TestIdempotentSnapshotCleanup(unittest.TestCase):
    def test_missing_snapshot_dir_allows_cleanup(self):
        from spell_sync.push_journal import safe_discard_txn_snapshots, txn_snapshot_root

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            txn_id = "00000000-0000-4000-8000-000000000099"
            expected = txn_snapshot_root(wordlist, txn_id)
            self.assertFalse(expected.exists())
            ok, detail = safe_discard_txn_snapshots(wordlist, txn_id, str(expected))
            self.assertTrue(ok)
            self.assertIsNone(detail)


class TestRecoverUnreadableDestination(unittest.TestCase):
    def test_existing_unreadable_hash_is_failed_not_restored(self):
        from spell_sync.push_journal import (
            JOURNAL_STATE_WRITING,
            RecoverResult,
            file_content_hash,
            recover_from_journal,
        )
        from tests.journal_test_utils import write_test_journal

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("live\n", encoding="utf-8")
            journal = write_test_journal(
                wordlist,
                state=JOURNAL_STATE_WRITING,
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            snap = Path(journal.wordlist_backup_path)
            snap.write_text("snap\n", encoding="utf-8")
            # Align journal hash_before with the snapshot we just wrote.
            from dataclasses import replace

            journal = replace(
                journal,
                wordlist_hash_before=file_content_hash(snap),
                wordlist_hash_after="b" * 64,
            )
            snap_resolved = snap.resolve()
            wordlist_resolved = wordlist.resolve()

            def _hash(path):
                resolved = Path(path).resolve()
                if resolved == snap_resolved:
                    return journal.wordlist_hash_before
                if resolved == wordlist_resolved:
                    return None
                return file_content_hash(path)

            with patch("spell_sync.push_journal.file_content_hash", side_effect=_hash):
                result = recover_from_journal(journal, dry_run=False)
            self.assertIsInstance(result, RecoverResult)
            self.assertIn("wordlist", result.failed)
            self.assertNotIn("wordlist", result.restored)
            self.assertEqual(wordlist.read_text(encoding="utf-8"), "live\n")


class TestBakPreservesHistoryOnCopyFailure(unittest.TestCase):
    def test_failed_copy_does_not_rotate_away_existing_bak(self):
        from spell_sync.io import create_bak_backup

        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "dict.txt"
            bak = Path(d) / "dict.txt.bak"
            older = Path(d) / "dict.txt.1.bak"
            target.write_text("new\n", encoding="utf-8")
            bak.write_text("prev\n", encoding="utf-8")
            older.write_text("older\n", encoding="utf-8")
            with patch("spell_sync.io.backup_keep_count", return_value=3):
                with patch("spell_sync.io.shutil.copy2", side_effect=OSError("disk full")):
                    ok = create_bak_backup(target)
            self.assertFalse(ok)
            self.assertEqual(bak.read_text(encoding="utf-8"), "prev\n")
            self.assertEqual(older.read_text(encoding="utf-8"), "older\n")


class TestLegacyTextReaderFailClosed(unittest.TestCase):
    def test_read_text_words_rejects_control_bytes(self):
        from spell_sync.io import read_text_words

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "dict.txt"
            path.write_bytes(b"good\n\x00bad\n")
            self.assertEqual(read_text_words(path, quiet=True), set())


class TestUnsafeLockProbeHonesty(unittest.TestCase):
    def test_symlink_lock_is_not_reported_idle(self):
        from spell_sync.operation_lock import lock_path_for_wordlist, read_active_operation_lock

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            lock_path = lock_path_for_wordlist(wordlist)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            target = Path(d) / "elsewhere"
            target.write_text("x", encoding="utf-8")
            lock_path.symlink_to(target)
            info = read_active_operation_lock(wordlist)
            self.assertIsNotNone(info)
            assert info is not None
            self.assertEqual(info.command, "unsafe-lock")


if __name__ == "__main__":
    unittest.main()
