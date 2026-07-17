#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""review command and interactive removal prompts."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import spell_sync.removal_review as removal_mod
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.sync_run import SyncRun


class TestReviewInteractive(unittest.TestCase):
    def test_review_removals_interactive_non_tty(self):
        with tempfile.TemporaryDirectory() as d:
            dict_path = os.path.join(d, "dict.txt")
            Path(dict_path).write_text("gone\n", encoding="utf-8")
            wordlist = os.path.join(d, "wordlist.txt")
            Path(wordlist).write_text("stay\n", encoding="utf-8")
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            with patch.object(removal_mod.sys.stdin, "isatty", return_value=False):
                self.assertTrue(removal_mod.review_removals_interactive(run))

    def test_review_removals_interactive_eof(self):
        with tempfile.TemporaryDirectory() as d:
            dict_path = os.path.join(d, "dict.txt")
            Path(dict_path).write_text("gone\n", encoding="utf-8")
            wordlist = os.path.join(d, "wordlist.txt")
            Path(wordlist).write_text("stay\n", encoding="utf-8")
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            with (
                patch.object(removal_mod.sys.stdin, "isatty", return_value=True),
                patch("builtins.input", side_effect=EOFError),
            ):
                self.assertIsNone(removal_mod.review_removals_interactive(run))

    def test_review_no_removals_returns_true(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            Path(wordlist).write_text("stay\n", encoding="utf-8")
            dict_path = os.path.join(d, "dict.txt")
            Path(dict_path).write_text("stay\n", encoding="utf-8")
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            self.assertTrue(removal_mod.review_removals_interactive(run))

    def test_review_removals_interactive_yes(self):
        with tempfile.TemporaryDirectory() as d:
            dict_path = os.path.join(d, "dict.txt")
            Path(dict_path).write_text("gone\n", encoding="utf-8")
            wordlist = os.path.join(d, "wordlist.txt")
            Path(wordlist).write_text("stay\n", encoding="utf-8")
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            with (
                patch.object(removal_mod.sys.stdin, "isatty", return_value=True),
                patch("builtins.input", return_value="y"),
            ):
                self.assertTrue(removal_mod.review_removals_interactive(run))

    def test_list_removals(self):
        with tempfile.TemporaryDirectory() as d:
            dict_path = os.path.join(d, "dict.txt")
            Path(dict_path).write_text("gone\n", encoding="utf-8")
            wordlist = os.path.join(d, "wordlist.txt")
            Path(wordlist).write_text("stay\n", encoding="utf-8")
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            diffs = removal_mod.list_removals(run)
            self.assertEqual(len(diffs), 1)
            self.assertEqual(diffs[0].to_remove, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
