#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI, pull/push, and guards interaction tests."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import spell_sync.cli as cli_mod
import spell_sync.command_helpers as command_helpers
import spell_sync.commands as commands
from spell_sync.cli_options import CliOptions
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import read_text_words, write_text_words
from spell_sync.sync_run import PushResult, SyncRun


class TestCliDispatch(unittest.TestCase):
    def test_default_command_is_status(self):
        with patch.dict(cli_mod.COMMANDS, {"status": lambda opts: 42}):
            with redirect_stdout(io.StringIO()):
                code = cli_mod.main(["spell-sync"])
            self.assertEqual(code, 42)

    def test_unknown_command_exit_code(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli_mod.main(["spell-sync", "no-such-cmd"])
        self.assertEqual(code, int(ExitCode.UNKNOWN_COMMAND))
        self.assertIn("unknown command", buf.getvalue())


class TestPullPushInteraction(unittest.TestCase):
    def test_pull_import_fail_skips_wordlist_done_line(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            abort = ExitCode.PUSH_ABORT
            with (
                patch.object(run, "pull_into_wordlist", return_value=abort),
                patch.object(commands, "sync_run_for", return_value=run),
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = commands.cmd_pull(CliOptions(yes=True, wordlist=wordlist))
                out = buf.getvalue()
                self.assertEqual(code, int(ExitCode.PUSH_ABORT))
                self.assertNotIn("wordlist:", out)

    def test_push_push_fail_no_push_done_line(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            abort = ExitCode.PUSH_ABORT
            with (
                patch.object(run, "push_from_wordlist", return_value=abort),
                patch.object(commands, "sync_run_for", return_value=run),
                patch.object(
                    commands,
                    "_running_apps_check_for_push",
                    return_value=True,
                ),
                patch.object(commands, "warn_missing_optional_apps"),
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = commands.cmd_push(CliOptions(yes=True, wordlist=wordlist))
                out = buf.getvalue()
                self.assertEqual(code, int(ExitCode.PUSH_ABORT))
                self.assertNotIn("applied", out)

    def test_format_push_done_with_skipped(self):
        result = PushResult(
            1744,
            ("macos", "sublime"),
            ("macos-applespell",),
        )
        message = command_helpers.format_push_done(result)
        self.assertIn("1744 words", message)
        self.assertIn("2 dictionaries", message)
        self.assertIn("skipped: macos-applespell", message)

    def test_cmd_push_done_line_lists_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            push_result = PushResult(1, ("a",), ("skipped-one",))
            with (
                patch.object(
                    commands,
                    "_running_apps_check_for_push",
                    return_value=True,
                ),
                patch.object(commands, "sync_run_for", return_value=run),
                patch.object(run, "push_from_wordlist", return_value=push_result),
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = commands.cmd_push(CliOptions(wordlist=wordlist))
                self.assertEqual(code, int(ExitCode.PARTIAL_PUSH))
                self.assertIn("skipped: skipped-one", buf.getvalue())

    def test_pull_then_push_skipped_when_guard_rejects(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(dict_path, ["beta"], "utf-8", False, quiet=True)
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
                    pull_code = commands.cmd_pull(CliOptions(yes=True, wordlist=wordlist))
                self.assertEqual(pull_code, int(ExitCode.OK))
            with (
                patch.object(commands, "sync_run_for", return_value=run),
                patch.object(
                    commands,
                    "_running_apps_check_for_push",
                    return_value=False,
                ),
                patch.object(commands, "warn_missing_optional_apps"),
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    push_code = commands.cmd_push(CliOptions(yes=True, wordlist=wordlist))
                out = buf.getvalue()
                self.assertEqual(push_code, int(ExitCode.CANCELLED))
                self.assertIn("Cancelled", out)
                self.assertEqual(run.load_wordlist(), {"alpha", "beta"})
                self.assertEqual(read_text_words(dict_path, quiet=True), {"beta"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
