#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI, pull/push, and guards interaction tests."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from service_test_utils import (
    executable_push_preview,
    patch_commands_service,
    patch_isolated_sync_run,
    push_execution,
)

import spell_sync.cli as cli_mod
import spell_sync.command_helpers as command_helpers
import spell_sync.commands as commands
from spell_sync.application.reports import PullPreview
from spell_sync.cli_options import CliOptions
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import read_text_words, write_text_words
from spell_sync.sync_run import PushResult
from tests.runtime_helpers import make_sync_run


class TestCliDispatch(unittest.TestCase):
    def test_no_arg_tty_launches_ui(self):
        with (
            patch.object(cli_mod.sys.stdin, "isatty", return_value=True),
            patch.object(cli_mod.sys.stdout, "isatty", return_value=True),
            patch.object(cli_mod, "cmd_ui", return_value=0) as cmd_ui,
        ):
            code = cli_mod.main(["spell-sync"])
        cmd_ui.assert_called_once()
        self.assertEqual(code, 0)

    def test_no_arg_non_tty_requires_command(self):
        with (
            patch.object(cli_mod.sys.stdin, "isatty", return_value=False),
            patch.object(cli_mod.sys.stdout, "isatty", return_value=False),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli_mod.main(["spell-sync"])
        self.assertEqual(code, 2)
        self.assertIn("requires a command", buf.getvalue())

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
            preview = PullPreview(
                wordlist_path=wordlist,
                additions=0,
                before_count=0,
                after_count=0,
                sources_used=(),
                sources_skipped=(),
                source_rows=(),
                warnings=(),
                created_at="2026-01-01T00:00:00+00:00",
                plan_identifier="blocked",
                merged_words=(),
                prepare_error=ExitCode.PUSH_ABORT,
            )
            with patch_commands_service(prepare_pull=preview):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = commands.cmd_pull(CliOptions(yes=True, wordlist=wordlist))
                out = buf.getvalue()
                self.assertEqual(code, int(ExitCode.PUSH_ABORT))
                self.assertNotIn("wordlist:", out)

    def test_push_push_fail_no_push_done_line(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            preview = executable_push_preview()
            execution = push_execution(ExitCode.PUSH_ABORT, preview=preview)
            with (
                patch_commands_service(
                    load_push_preview=preview,
                    execute_push_preview=execution,
                    build_push_report=MagicMock(),
                ),
                patch.object(
                    commands,
                    "_running_apps_check_for_push",
                    return_value=True,
                ),
                patch.object(commands, "confirm_push_removals_for_preview", return_value=True),
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
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            push_result = PushResult(1, ("a",), ("skipped-one",))
            preview = executable_push_preview()
            execution = push_execution(push_result, preview=preview)
            with (
                patch.object(
                    commands,
                    "_running_apps_check_for_push",
                    return_value=True,
                ),
                patch.object(commands, "confirm_push_removals_for_preview", return_value=True),
                patch_commands_service(
                    load_push_preview=preview,
                    execute_push_preview=execution,
                    build_push_report=MagicMock(),
                ),
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
            run = make_sync_run(
                wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            preview = executable_push_preview()
            with patch_isolated_sync_run(run):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    pull_code = commands.cmd_pull(CliOptions(yes=True, wordlist=wordlist))
                self.assertEqual(pull_code, int(ExitCode.OK))
            with (
                patch_commands_service(load_push_preview=preview),
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
                self.assertEqual(read_text_words(wordlist, quiet=True), {"alpha", "beta"})
                self.assertEqual(read_text_words(dict_path, quiet=True), {"beta"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
