#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for command_helpers, paths resolution, and commands coverage."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from conftest import DEFAULT_OPTS

import spell_sync.command_helpers as command_helpers
import spell_sync.commands as commands
from spell_sync.cli_options import CliOptions
from spell_sync.command_helpers import finish_push, sync_run_for, wordlist_file_for
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import write_text_words
from spell_sync.paths import resolve_wordlist_path
from spell_sync.sync_run import PushResult, SyncRun


class TestResolveWordlistPath(unittest.TestCase):
    def test_explicit_path(self):
        self.assertEqual(
            resolve_wordlist_path("/tmp/custom.txt"),
            Path("/tmp/custom.txt"),
        )

    def test_default_uses_project_root(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "spell-sync"\n', encoding="utf-8"
            )
            (root / "spell_sync").mkdir()
            sub = root / "nested"
            sub.mkdir()
            with patch("spell_sync.paths.Path.cwd", return_value=sub):
                self.assertEqual(resolve_wordlist_path(), root / "wordlist.txt")

    def test_cli_options_wordlist(self):
        with tempfile.TemporaryDirectory() as d:
            custom = os.path.join(d, "words.txt")
            Path(custom).write_text("a\n", encoding="utf-8")
            opts = CliOptions(wordlist=custom)
            self.assertEqual(wordlist_file_for(opts), Path(custom))

    def test_sync_run_for_uses_explicit_wordlist(self):
        with tempfile.TemporaryDirectory() as d:
            custom = os.path.join(d, "words.txt")
            Path(custom).write_text("a\n", encoding="utf-8")
            run = sync_run_for(CliOptions(wordlist=custom))
            self.assertEqual(str(run.wordlist_file), custom)

    def test_finish_push_json_partial(self):
        result = PushResult(2, ("a",), ("skip",))
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = finish_push(result, CliOptions(json_output=True))
        self.assertEqual(code, int(ExitCode.PARTIAL_PUSH))
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["partial"])
        self.assertEqual(payload["exit"], int(ExitCode.PARTIAL_PUSH))
        self.assertIn("skipped_reasons", payload)
        self.assertIn("skipped_details", payload)


class TestCommandHelpers(unittest.TestCase):
    def test_dictionaries_label_plurals(self):
        cases = {
            0: "0 dictionaries",
            1: "1 dictionary",
            2: "2 dictionaries",
            5: "5 dictionaries",
            11: "11 dictionaries",
            21: "21 dictionaries",
            22: "22 dictionaries",
        }
        for count, expected in cases.items():
            with self.subTest(count=count):
                self.assertEqual(command_helpers.dictionaries_label(count), expected)

    def test_guard_exit_code(self):
        self.assertIsNone(command_helpers.guard_exit_code(True, cancelled=ExitCode.CANCELLED))
        self.assertEqual(
            command_helpers.guard_exit_code(None, cancelled=ExitCode.CANCELLED),
            int(ExitCode.SYNC_INTERRUPTED),
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = command_helpers.guard_exit_code(False, cancelled=ExitCode.CANCELLED)
        self.assertEqual(code, int(ExitCode.CANCELLED))
        self.assertIn("Cancelled", buf.getvalue())

    def test_confirm_push_removals_non_interactive_aborts(self):
        run = SyncRun(wordlist="/tmp/x", dictionaries=[])
        run.max_push_removals = lambda: 100  # type: ignore[method-assign]
        with (
            patch.object(command_helpers, "push_max_removals_without_confirm", return_value=5),
            patch.object(command_helpers.sys, "stdin") as stdin,
        ):
            stdin.isatty.return_value = False
            self.assertFalse(
                command_helpers.confirm_push_removals(run, CliOptions(json_output=False))
            )


class TestCommandsJson(unittest.TestCase):
    def test_cmd_pull_json(self):
        run = SyncRun(wordlist="/tmp/x", dictionaries=[])
        run.pull_into_wordlist = lambda: (1, 3)  # type: ignore[method-assign]
        with patch.object(commands, "sync_run_for", return_value=run):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = commands.cmd_pull(CliOptions(json_output=True))
            self.assertEqual(code, 0)
            data = json.loads(buf.getvalue())
            self.assertEqual(data["added"], 2)

    def test_cmd_pull_abort_json(self):
        run = SyncRun(wordlist="/tmp/x", dictionaries=[])
        run.pull_into_wordlist = lambda: ExitCode.WORDLIST_UNREADABLE  # type: ignore
        with patch.object(commands, "sync_run_for", return_value=run):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = commands.cmd_pull(CliOptions(json_output=True))
            self.assertEqual(code, int(ExitCode.WORDLIST_UNREADABLE))
            self.assertEqual(json.loads(buf.getvalue())["exit"], int(ExitCode.WORDLIST_UNREADABLE))

    def test_cmd_push_json_success(self):
        result = PushResult(2, ("a", "b"), ())
        with (
            patch.object(commands, "warn_missing_optional_apps"),
            patch.object(commands, "_running_apps_check_for_push", return_value=True),
            patch.object(commands, "confirm_push_removals", return_value=True),
            patch.object(commands, "sync_run_for") as run_cls,
        ):
            run_cls.return_value.push_from_wordlist.return_value = result
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = commands.cmd_push(CliOptions(json_output=True))
            self.assertEqual(code, 0)
            data = json.loads(buf.getvalue())
            self.assertEqual(data["written"], ["a", "b"])
            self.assertEqual(data["exit"], 0)

    def test_cmd_push_json_abort(self):
        with (
            patch.object(commands, "warn_missing_optional_apps"),
            patch.object(commands, "_running_apps_check_for_push", return_value=True),
            patch.object(commands, "confirm_push_removals", return_value=True),
            patch.object(commands, "sync_run_for") as run_cls,
        ):
            run_cls.return_value.push_from_wordlist.return_value = ExitCode.PUSH_ABORT
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = commands.cmd_push(CliOptions(json_output=True))
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))

    def test_cmd_push_dry_run_json_skips_diff_print(self):
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
                patch.object(commands, "sync_run_for", return_value=run),
                patch.object(commands, "warn_missing_optional_apps"),
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = commands.cmd_push(
                        CliOptions(dry_run=True, json_output=True),
                    )
            data = json.loads(buf.getvalue())
            self.assertEqual(code, 0)
            self.assertTrue(data["dry_run"])
            self.assertNotIn("stale", buf.getvalue())

    def test_cmd_lint_json(self):
        with patch.object(commands, "run_lint", return_value=ExitCode.LINT_FAILED):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = commands.cmd_lint(CliOptions(json_output=True, strict=True))
            self.assertEqual(code, int(ExitCode.LINT_FAILED))
            self.assertEqual(json.loads(buf.getvalue())["exit"], int(ExitCode.LINT_FAILED))


class TestCommandsSyncFlow(unittest.TestCase):
    def test_cmd_pull_text_success(self):
        run = SyncRun(wordlist="/tmp/x", dictionaries=[])
        run.pull_into_wordlist = lambda: (2, 5)  # type: ignore[method-assign]
        with patch.object(commands, "sync_run_for", return_value=run):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = commands.cmd_pull(DEFAULT_OPTS)
            self.assertEqual(code, 0)
            self.assertIn("wordlist:", buf.getvalue())

    def test_running_apps_check_for_push_delegates(self):
        with (
            patch.object(commands.sys, "stdin") as stdin,
            patch.object(commands, "confirm_chrome_before_push", return_value=True) as chrome,
            patch.object(commands, "confirm_firefox_before_push", return_value=True) as firefox,
        ):
            stdin.isatty.return_value = True
            self.assertTrue(commands._running_apps_check_for_push(DEFAULT_OPTS))
            chrome.assert_called_once_with(interactive=True)
            firefox.assert_called_once_with(interactive=True)

    def test_running_apps_check_for_push_yes_skips_prompt(self):
        with (
            patch.object(commands.sys, "stdin") as stdin,
            patch.object(commands, "confirm_chrome_before_push", return_value=True) as chrome,
            patch.object(commands, "confirm_firefox_before_push", return_value=True) as firefox,
        ):
            stdin.isatty.return_value = True
            self.assertTrue(commands._running_apps_check_for_push(CliOptions(yes=True)))
            chrome.assert_called_once_with(interactive=False)
            firefox.assert_called_once_with(interactive=False)

    def test_status_unreadable_json(self):
        run = SyncRun(wordlist="/tmp/x", dictionaries=[])
        run.check_wordlist = lambda: ExitCode.WORDLIST_UNREADABLE  # type: ignore
        with patch.object(commands, "sync_run_for", return_value=run):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = commands.cmd_status(CliOptions(json_output=True))
            self.assertEqual(code, int(ExitCode.WORDLIST_UNREADABLE))
            self.assertEqual(
                json.loads(buf.getvalue())["exit"],
                int(ExitCode.WORDLIST_UNREADABLE),
            )

    def test_status_warns_destructive_push_risk(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["a"], "utf-8", False, quiet=True)
            write_text_words(
                dict_path,
                [f"w{i}" for i in range(25)],
                "utf-8",
                False,
                quiet=True,
            )
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            with patch.object(commands, "sync_run_for", return_value=run):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = commands.cmd_status(DEFAULT_OPTS)
            self.assertEqual(code, 0)
            self.assertIn("run `pull` first", buf.getvalue())

    def test_cmd_init_json(self):
        with tempfile.TemporaryDirectory() as d:
            previous = os.getcwd()
            try:
                os.chdir(d)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = commands.cmd_init(CliOptions(json_output=True))
                self.assertEqual(code, 0)
                payload = json.loads(buf.getvalue())
                self.assertIn("created", payload)
            finally:
                os.chdir(previous)

    def test_cmd_init_nothing_to_create(self):
        with tempfile.TemporaryDirectory() as d:
            previous = os.getcwd()
            try:
                os.chdir(d)
                commands.cmd_init(CliOptions())
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = commands.cmd_init(DEFAULT_OPTS)
                self.assertEqual(code, 0)
                self.assertIn("already exist", buf.getvalue())
            finally:
                os.chdir(previous)


class TestLogOutput(unittest.TestCase):
    def test_dictionary_status_and_verbose_diff(self):
        import spell_sync.log as log_mod

        log = log_mod.Log(quiet=False)
        buf = io.StringIO()
        with redirect_stdout(buf):
            log.dictionary_status("macos", 10, 8, 2, 0)
            log.dictionary_word_diff("добавить", tuple(f"w{i}" for i in range(20)))
        out = buf.getvalue()
        self.assertIn("macos:", out)
        self.assertIn("… (+8)", out)

    def test_lint_item_and_note(self):
        import spell_sync.log as log_mod

        log = log_mod.Log(quiet=False)
        buf = io.StringIO()
        with redirect_stdout(buf):
            log.lint_item("detail")
            log.lint_note("note")
        self.assertIn("detail", buf.getvalue())
        self.assertIn("note", buf.getvalue())

    def test_quiet_skips_lint_item_and_note(self):
        import spell_sync.log as log_mod

        log = log_mod.Log(quiet=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            log.lint_item("hidden")
            log.lint_note("hidden")
        self.assertEqual(buf.getvalue(), "")

    def test_quiet_skips_status_and_lint(self):
        import spell_sync.log as log_mod

        log = log_mod.Log(quiet=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            log.dictionary_status("x", 1, 1, 0, 0)
            log.lint_group("test", 1)
            log.detail("hidden")
        self.assertEqual(buf.getvalue(), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
