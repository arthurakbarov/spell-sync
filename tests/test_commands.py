#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI command integration tests."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

from conftest import DEFAULT_OPTS

import spell_sync.commands as commands
from spell_sync.cli_options import CliOptions
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import write_text_words
from spell_sync.sync_run import PushResult, SyncRun


class TestCommands(unittest.TestCase):
    def _dictionaries(self, path_a: str, path_b: str):
        return [
            Dictionary("a", path_a, DictionaryFormat.TEXT),
            Dictionary("b", path_b, DictionaryFormat.TEXT),
        ]

    def _write_fixture(self, wordlist, path_a, path_b):
        write_text_words(wordlist, ["alpha", "beta"], "utf-8", False, quiet=True)
        write_text_words(path_a, ["alpha"], "utf-8", False, quiet=True)
        write_text_words(
            path_b,
            ["alpha", "beta", "extra"],
            "utf-8",
            False,
            quiet=True,
        )

    def test_cmd_status(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            path_a = os.path.join(d, "a.txt")
            path_b = os.path.join(d, "b.txt")
            self._write_fixture(wordlist, path_a, path_b)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=self._dictionaries(path_a, path_b),
            )
            with patch("spell_sync.commands.sync_run_for", return_value=run):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    self.assertEqual(commands.cmd_status(DEFAULT_OPTS), 0)
                out = buf.getvalue()
                self.assertIn("a:", out)
                self.assertIn("+1", out)
                self.assertIn("-1", out)
                self.assertNotIn("add (push)", out)

    def test_cmd_status_verbose_shows_words(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            path_a = os.path.join(d, "a.txt")
            path_b = os.path.join(d, "b.txt")
            self._write_fixture(wordlist, path_a, path_b)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=self._dictionaries(path_a, path_b),
            )
            with patch("spell_sync.commands.sync_run_for", return_value=run):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = commands.cmd_status(CliOptions(verbose=True))
                    self.assertEqual(code, 0)
                out = buf.getvalue()
                self.assertIn("(verbose)", out)
                self.assertIn("beta", out)
                self.assertIn("extra", out)


class TestWordlistUnreadable(unittest.TestCase):
    def test_pull_aborts_when_wordlist_unreadable(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            with open(wordlist, "w", encoding="utf-8") as handle:
                handle.write("alpha\n")
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            with patch("spell_sync.push_setup.wordlist_unreadable", return_value=True):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    result = run.pull_into_wordlist()
                self.assertEqual(result, ExitCode.WORDLIST_UNREADABLE)
                self.assertIn("wordlist unreadable", buf.getvalue())

    def test_cmd_status_returns_wordlist_unreadable(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            open(wordlist, "w").close()
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            with (
                patch("spell_sync.commands.sync_run_for", return_value=run),
                patch("spell_sync.push_setup.wordlist_unreadable", return_value=True),
            ):
                code = commands.cmd_status(DEFAULT_OPTS)
            self.assertEqual(code, int(ExitCode.WORDLIST_UNREADABLE))


class TestPartialPushExit(unittest.TestCase):
    def test_run_partial_push_exit_via_command(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            result = PushResult(1, ("a",), ("blocked",))
            with (
                patch.object(commands, "_running_apps_check_for_push", return_value=True),
                patch.object(commands, "sync_run_for", return_value=run),
                patch.object(run, "push_from_wordlist", return_value=result),
            ):
                code = commands.cmd_push(DEFAULT_OPTS)
            self.assertEqual(code, int(ExitCode.PARTIAL_PUSH))


class TestPushReviewRemovals(unittest.TestCase):
    def test_push_review_removals_interrupted(self):
        run = SyncRun(wordlist="/tmp/x", dictionaries=[])
        prepared = MagicMock()
        prepared.max_removals.return_value = 0
        with (
            patch.object(commands, "_running_apps_check_for_push", return_value=True),
            patch.object(commands, "sync_run_for", return_value=run),
            patch.object(run, "prepare_push_operation", return_value=prepared),
            patch.object(commands, "review_removals_interactive", return_value=None),
        ):
            code = commands.cmd_push(CliOptions(review_removals=True))
        self.assertEqual(code, int(ExitCode.SYNC_INTERRUPTED))

    def test_before_push_checks_review_removals_false(self):
        run = SyncRun(wordlist="/tmp/x", dictionaries=[])
        with (
            patch.object(commands, "_running_apps_check_for_push", return_value=True),
            patch.object(commands, "review_removals_interactive", return_value=False),
        ):
            result = commands._before_push_checks(run, CliOptions(review_removals=True))
        self.assertFalse(result)

    def test_before_push_checks_running_apps_rejected(self):
        run = SyncRun(wordlist="/tmp/x", dictionaries=[])
        with patch.object(commands, "_running_apps_check_for_push", return_value=False):
            self.assertFalse(commands._before_push_checks(run, DEFAULT_OPTS))

    def test_before_push_checks_running_apps_interrupted(self):
        run = SyncRun(wordlist="/tmp/x", dictionaries=[])
        with patch.object(commands, "_running_apps_check_for_push", return_value=None):
            self.assertIsNone(commands._before_push_checks(run, DEFAULT_OPTS))


class TestPullAddFrom(unittest.TestCase):
    def test_merges_external_file(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            Path(wordlist).write_text("alpha\n", encoding="utf-8")
            external = os.path.join(d, "extra.txt")
            Path(external).write_text("beta\ngamma\n", encoding="utf-8")
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            result = run.pull_add_from(external)
            self.assertIsInstance(result, tuple)
            before, after = result
            self.assertEqual(before, 1)
            self.assertEqual(after, 3)

    def test_cmd_pull_add_from(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            Path(wordlist).write_text("one\n", encoding="utf-8")
            external = os.path.join(d, "from.txt")
            Path(external).write_text("two\n", encoding="utf-8")
            with patch.object(commands, "sync_run_for") as factory:
                run = SyncRun(wordlist=wordlist, dictionaries=[])
                factory.return_value = run
                code = commands.cmd_pull(CliOptions(add_from=external, wordlist=wordlist))
            self.assertEqual(code, int(ExitCode.OK))
            words = run.load_wordlist()
            self.assertIn("one", words)
            self.assertIn("two", words)


if __name__ == "__main__":
    unittest.main(verbosity=2)
