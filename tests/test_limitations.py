#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for documented edge-case limitations."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import spell_sync.lint as lint_mod
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import read_text_words, write_text_words
from spell_sync.sync_run import PushResult, SyncRun


class TestLimitationBackupFail(unittest.TestCase):
    """Failed backup — dictionary is not written, content unchanged."""

    def test_backup_fail_skips_write_leaves_dictionary_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            path_a = os.path.join(d, "a.txt")
            path_b = os.path.join(d, "b.txt")
            words = ["alpha", "beta"]
            write_text_words(wordlist, words, "utf-8", False, quiet=True)
            write_text_words(path_a, ["stale-a"], "utf-8", False, quiet=True)
            write_text_words(path_b, ["stale-b"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[
                    Dictionary("a", path_a, DictionaryFormat.TEXT),
                    Dictionary("b", path_b, DictionaryFormat.TEXT),
                ],
            )
            original_copy2 = shutil.copy2

            def flaky_copy2(src, dst, *args, **kwargs):
                if os.path.basename(str(src)) == "a.txt":
                    raise OSError("backup failed")
                return original_copy2(src, dst, *args, **kwargs)

            def flaky_render(path, rendered):
                if Path(path).name == "b.txt":
                    return False
                return True

            with (
                patch("spell_sync.push_transaction.shutil.copy2", flaky_copy2),
                patch("spell_sync.push_prepared.write_rendered", flaky_render),
            ):
                result = run.push_from_wordlist()

            self.assertEqual(result, ExitCode.PUSH_ABORT)
            self.assertEqual(
                read_text_words(path_a, quiet=True),
                {"stale-a"},
            )
            self.assertEqual(
                read_text_words(path_b, quiet=True),
                {"stale-b"},
            )

    def test_push_aborts_when_all_backups_fail(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(dict_path, ["stale"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            side_effect = OSError("snap fail")
            with patch(
                "spell_sync.push_transaction.shutil.copy2",
                side_effect=side_effect,
            ):
                result = run.push_from_wordlist()
            self.assertEqual(result, ExitCode.PUSH_ABORT)
            self.assertEqual(read_text_words(dict_path, quiet=True), {"stale"})
            self.assertEqual(run.load_wordlist(), {"alpha"})

    def test_all_dictionary_backups_fail_rolls_back_wordlist(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            with open(wordlist, "w", encoding="utf-8") as handle:
                handle.write("alpha\n")
            write_text_words(dict_path, ["stale"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            original_copy2 = shutil.copy2

            def flaky_copy2(src, dst, *args, **kwargs):
                if os.path.basename(str(src)) == "a.txt":
                    raise OSError("backup failed")
                return original_copy2(src, dst, *args, **kwargs)

            with patch("spell_sync.push_transaction.shutil.copy2", flaky_copy2):
                result = run.push_from_wordlist()

            self.assertEqual(result, ExitCode.PUSH_ABORT)
            with open(wordlist, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "alpha\n")
            self.assertEqual(read_text_words(dict_path, quiet=True), {"stale"})


class TestLimitationReadableProxy(unittest.TestCase):
    """Unreadable dictionary is skipped during push (is_path_readable)."""

    def test_unreadable_dictionary_skipped_on_push(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "blocked.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(dict_path, ["only-here"], "utf-8", False, quiet=True)
            blocked_dict = Dictionary("blocked", dict_path, DictionaryFormat.TEXT)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[blocked_dict],
            )
            with patch("spell_sync.read_outcome.is_path_readable", return_value=False):
                result = run.push_from_wordlist()
            self.assertIsInstance(result, PushResult)
            assert not isinstance(result, ExitCode)
            self.assertEqual(result.skipped, ("blocked",))
            self.assertEqual(read_text_words(dict_path, quiet=True), {"only-here"})

    def test_readable_dictionary_write_fail_rolls_back(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(dict_path, ["stale"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            with (
                patch("spell_sync.read_outcome.is_path_readable", return_value=True),
                patch("spell_sync.push_prepared.write_rendered", return_value=False),
            ):
                result = run.push_from_wordlist()
            self.assertEqual(result, ExitCode.PUSH_ABORT)
            self.assertEqual(read_text_words(dict_path, quiet=True), {"stale"})


class TestLimitationBlockedImport(unittest.TestCase):
    """Blocked dictionary — import does not pull words."""

    def test_pull_does_not_union_from_unreadable_dictionary(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            blocked = os.path.join(d, "blocked.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(blocked, ["secret"], "utf-8", False, quiet=True)
            blocked_dict = Dictionary("blocked", blocked, DictionaryFormat.TEXT)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[blocked_dict],
            )

            from spell_sync.read_outcome import (
                DictionaryReadResult,
                ReadStatus,
                dictionary_read_result,
            )

            real = dictionary_read_result

            def mock_read(dictionary):
                if dictionary.path == blocked:
                    return DictionaryReadResult(ReadStatus.UNREADABLE, frozenset(), "blocked", None)
                return real(dictionary)

            with patch("spell_sync.push_setup.dictionary_read_result", mock_read):
                result = run.pull_into_wordlist()

            self.assertEqual(result, (1, 1))
            self.assertEqual(run.load_wordlist(), {"alpha"})


class TestLimitationLintStrict(unittest.TestCase):
    def test_lint_strict_returns_lint_failed_on_issues(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            with open(wordlist, "w", encoding="utf-8") as handle:
                handle.write("ok\nbad word\n")
            code = lint_mod.run_lint(wordlist, fix=False, strict=True)
            self.assertEqual(int(code), int(ExitCode.LINT_FAILED))


class TestDestructivePushGuard(unittest.TestCase):
    """Block push when tiny wordlist would wipe large local dictionaries."""

    def test_push_aborts_when_wordlist_tiny_and_local_large(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "dict.txt")
            write_text_words(wordlist, ["a", "b", "c"], "utf-8", False, quiet=True)
            write_text_words(
                dict_path,
                [f"word{i}" for i in range(30)],
                "utf-8",
                False,
                quiet=True,
            )
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("s", dict_path, DictionaryFormat.TEXT)],
            )
            result = run.push_from_wordlist()
            self.assertEqual(result, ExitCode.PUSH_ABORT)
            stale = {f"word{i}" for i in range(30)}
            self.assertEqual(read_text_words(dict_path, quiet=True), stale)

    def test_push_allowed_when_wordlist_large_enough(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "dict.txt")
            words = [f"word{i}" for i in range(15)]
            write_text_words(wordlist, words, "utf-8", False, quiet=True)
            write_text_words(dict_path, ["stale"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("s", dict_path, DictionaryFormat.TEXT)],
            )
            result = run.push_from_wordlist()
            self.assertEqual(result.written, ("s",))

    def test_dry_run_also_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "dict.txt")
            write_text_words(wordlist, ["only"], "utf-8", False, quiet=True)
            write_text_words(
                dict_path,
                [f"w{i}" for i in range(25)],
                "utf-8",
                False,
                quiet=True,
            )
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("s", dict_path, DictionaryFormat.TEXT)],
            )
            result = run.plan_push()
            self.assertEqual(result, ExitCode.PUSH_ABORT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
