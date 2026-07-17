#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for push --dry-run."""

import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import spell_sync.commands as commands
from spell_sync.cli_options import CliOptions
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.io import read_text_words, write_text_words
from spell_sync.sync_run import SyncRun


class TestDryRun(unittest.TestCase):
    def test_plan_push_does_not_write(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(dict_path, ["stale"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            result = run.plan_push()
            self.assertEqual(result.word_count, 1)
            self.assertEqual(result.written, ("a",))
            self.assertEqual(read_text_words(dict_path, quiet=True), {"stale"})
            self.assertFalse(os.path.exists(dict_path + ".bak"))
            self.assertFalse(os.path.exists(wordlist + ".bak"))

    def test_plan_push_skips_dictionary_when_backup_fails(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            path_a = os.path.join(d, "a.txt")
            path_b = os.path.join(d, "b.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
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

            with patch("spell_sync.push_transaction.shutil.copy2", flaky_copy2):
                result = run.plan_push()

            self.assertEqual(result.written, ("b",))
            self.assertEqual(result.skipped, ("a",))
            self.assertEqual(read_text_words(path_a, quiet=True), {"stale-a"})

    def test_plan_push_matches_push_writable_set(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            path_a = os.path.join(d, "a.txt")
            path_b = os.path.join(d, "b.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
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

            with patch("spell_sync.push_transaction.shutil.copy2", flaky_copy2):
                plan = run.plan_push()
                push = run.push_from_wordlist()

            self.assertEqual(plan.written, push.written)
            self.assertEqual(plan.skipped, push.skipped)

    def test_cmd_push_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["alpha", "beta"], "utf-8", False, quiet=True)
            write_text_words(dict_path, ["stale"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            with (
                patch.object(commands, "sync_run_for", return_value=run),
                patch.object(commands, "warn_missing_optional_apps"),
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = commands.cmd_push(CliOptions(dry_run=True))
                out = buf.getvalue()
                self.assertEqual(code, 0)
                self.assertIn("dry-run", out)
                self.assertIn("no writes performed", out)
                self.assertEqual(read_text_words(dict_path, quiet=True), {"stale"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
