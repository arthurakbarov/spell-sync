#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Risk mitigation tests: strict push, Firefox guard, removal warnings."""

from __future__ import annotations

import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from conftest import DEFAULT_OPTS

import spell_sync.command_helpers as command_helpers
import spell_sync.commands as commands
import spell_sync.lint as lint_mod
from spell_sync.cli_options import CliOptions
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import read_text_words, write_text_words
from spell_sync.skip_reasons import PushSkipReason
from spell_sync.sync_run import PushResult, SyncRun


class TestPushStrict(unittest.TestCase):
    def test_strict_aborts_on_skipped_unreadable(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            path_ok = os.path.join(d, "ok.txt")
            path_blocked = os.path.join(d, "blocked.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(path_ok, ["stale"], "utf-8", False, quiet=True)
            write_text_words(path_blocked, ["x"], "utf-8", False, quiet=True)
            dictionaries = [
                Dictionary("ok", path_ok, DictionaryFormat.TEXT),
                Dictionary("blocked", path_blocked, DictionaryFormat.TEXT),
            ]
            run = SyncRun(wordlist=wordlist, dictionaries=dictionaries, strict_push=True)

            def readable(path):
                return str(path) != path_blocked

            patch_target = "spell_sync.read_outcome.is_path_readable"
            with patch(patch_target, side_effect=lambda p: readable(p)):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    result = run.push_from_wordlist()
                self.assertEqual(result, ExitCode.PUSH_ABORT)
                self.assertIn("--strict", buf.getvalue())
                self.assertEqual(read_text_words(path_ok, quiet=True), {"stale"})

    def test_strict_aborts_on_partial_backup_failure(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            path_ok = os.path.join(d, "ok.txt")
            path_fail = os.path.join(d, "fail.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(path_ok, ["stale"], "utf-8", False, quiet=True)
            write_text_words(path_fail, ["x"], "utf-8", False, quiet=True)
            dictionaries = [
                Dictionary("ok", path_ok, DictionaryFormat.TEXT),
                Dictionary("fail", path_fail, DictionaryFormat.TEXT),
            ]
            run = SyncRun(wordlist=wordlist, dictionaries=dictionaries, strict_push=True)
            original_copy2 = shutil.copy2

            def selective_copy2(src, dst, *args, **kwargs):
                if os.path.basename(str(src)) == "fail.txt":
                    raise OSError("backup failed")
                return original_copy2(src, dst, *args, **kwargs)

            with patch("spell_sync.push_transaction.shutil.copy2", selective_copy2):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    result = run.push_from_wordlist()
            self.assertEqual(result, ExitCode.PUSH_ABORT)
            self.assertIn("--strict", buf.getvalue())
            self.assertIn("backup failed", buf.getvalue())
            self.assertEqual(read_text_words(path_ok, quiet=True), {"stale"})
            self.assertEqual(read_text_words(path_fail, quiet=True), {"x"})

    def test_non_strict_partial_push_still_works(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            path_ok = os.path.join(d, "ok.txt")
            path_blocked = os.path.join(d, "blocked.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(path_ok, ["stale"], "utf-8", False, quiet=True)
            write_text_words(path_blocked, ["x"], "utf-8", False, quiet=True)
            dictionaries = [
                Dictionary("ok", path_ok, DictionaryFormat.TEXT),
                Dictionary("blocked", path_blocked, DictionaryFormat.TEXT),
            ]
            run = SyncRun(wordlist=wordlist, dictionaries=dictionaries, strict_push=False)

            def readable(path):
                return str(path) != path_blocked

            patch_target = "spell_sync.read_outcome.is_path_readable"
            with patch(patch_target, side_effect=lambda p: readable(p)):
                result = run.push_from_wordlist()
            self.assertEqual(result.skipped, ("blocked",))

    def test_cmd_push_strict_via_cli(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
                strict_push=True,
            )
            with (
                patch.object(commands, "_running_apps_check_for_push", return_value=True),
                patch.object(commands, "sync_run_for", return_value=run),
                patch.object(run, "push_from_wordlist", return_value=ExitCode.PUSH_ABORT),
            ):
                code = commands.cmd_push(CliOptions(strict=True))
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))

    def test_finish_push_partial_summary_line(self):
        result = PushResult(
            2,
            ("a",),
            ("skip-dict",),
            {"skip-dict": PushSkipReason.UNREADABLE},
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = command_helpers.finish_push(result, DEFAULT_OPTS)
        self.assertEqual(code, int(ExitCode.PARTIAL_PUSH))
        out = buf.getvalue()
        self.assertIn("partial push (exit 5)", out)
        self.assertIn("skip-dict", out)
        self.assertIn("unreadable", out)
        self.assertIn("push --strict", out)


class TestFirefoxGuard(unittest.TestCase):
    def test_skips_when_firefox_disabled(self):
        import spell_sync.app_process_check as guard

        with patch.object(guard, "firefox_dictionaries_enabled", return_value=False):
            self.assertTrue(guard.confirm_firefox_before_push(interactive=True))

    def test_skips_when_firefox_not_running(self):
        import spell_sync.app_process_check as guard

        with (
            patch.object(guard, "firefox_dictionaries_enabled", return_value=True),
            patch.object(guard, "is_firefox_running", return_value=False),
        ):
            self.assertTrue(guard.confirm_firefox_before_push(interactive=True))

    def test_non_interactive_warns_and_proceeds(self):
        import spell_sync.app_process_check as guard

        with (
            patch.object(guard, "firefox_dictionaries_enabled", return_value=True),
            patch.object(guard, "is_firefox_running", return_value=True),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertTrue(guard.confirm_firefox_before_push(interactive=False))
            self.assertIn("Firefox is running", buf.getvalue())

    def test_running_apps_check_also_runs_firefox(self):
        with (
            patch.object(commands, "confirm_chrome_before_push", return_value=True),
            patch.object(commands, "confirm_firefox_before_push", return_value=False),
        ):
            self.assertFalse(commands._running_apps_check_for_push(DEFAULT_OPTS))

    def test_pgrep_running_interpretation(self):
        import spell_sync.app_process_check as guard

        self.assertTrue(guard._pgrep_running(0))
        self.assertFalse(guard._pgrep_running(1))
        self.assertIsNone(guard._pgrep_running(2))

    def test_is_firefox_running_macos_dispatch(self):
        import spell_sync.app_process_check as guard

        with (
            patch.object(guard, "is_windows", return_value=False),
            patch.object(guard.sys, "platform", "darwin"),
            patch.object(guard, "_macos_pgrep_first_running", return_value=True) as mac,
        ):
            self.assertTrue(guard.is_firefox_running())
            mac.assert_called_once_with("firefox", "Firefox")

    def test_is_firefox_running_windows(self):
        import spell_sync.app_process_check as guard

        with (
            patch.object(guard, "is_windows", return_value=True),
            patch.object(guard, "_windows_exe_running", return_value=True) as win,
        ):
            self.assertTrue(guard.is_firefox_running())
            win.assert_called_once_with("firefox.exe")

    def test_macos_pgrep_first_running_os_error(self):
        import spell_sync.app_process_check as guard

        with patch.object(
            guard.subprocess,
            "run",
            side_effect=OSError("pgrep missing"),
        ):
            self.assertIsNone(guard._macos_pgrep_first_running("firefox", "Firefox"))

    def test_macos_pgrep_first_running_tries_next_pattern(self):
        import spell_sync.app_process_check as guard

        def fake_run(cmd, **kwargs):
            name = cmd[-1]
            rc = 0 if name == "Firefox" else 1
            return type("R", (), {"returncode": rc})()

        with patch.object(guard.subprocess, "run", side_effect=fake_run):
            self.assertTrue(guard._macos_pgrep_first_running("firefox", "Firefox"))

    def test_confirm_when_check_fails_non_interactive(self):
        import spell_sync.app_process_check as guard

        with (
            patch.object(guard, "firefox_dictionaries_enabled", return_value=True),
            patch.object(guard, "is_firefox_running", return_value=None),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertTrue(guard.confirm_firefox_before_push(interactive=False))
            self.assertIn("Could not check whether Firefox is running", buf.getvalue())

    def test_doctor_warns_firefox_running(self):
        import spell_sync.doctor as doctor_mod
        import spell_sync.health.report as report_mod

        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            with (
                patch.object(report_mod, "firefox_dictionaries_enabled", return_value=True),
                patch.object(report_mod, "is_firefox_running", return_value=True),
            ):
                report = doctor_mod.build_doctor_report(run)
            messages = [c.message for c in report.checks]
            self.assertTrue(any("Firefox is running" in m for m in messages))


class TestRemovalWarning(unittest.TestCase):
    def test_confirm_push_removals_prompts_when_over_limit(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["keep"], "utf-8", False, quiet=True)
            many = [f"word{i}" for i in range(60)]
            write_text_words(dict_path, ["keep", *many], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            limit_patch = "spell_sync.command_helpers.push_max_removals_without_confirm"
            with (
                patch(limit_patch, return_value=50),
                patch("builtins.input", return_value="n"),
                patch.object(commands.sys, "stdin") as stdin,
            ):
                stdin.isatty.return_value = True
                self.assertFalse(command_helpers.confirm_push_removals(run, DEFAULT_OPTS))

    def test_confirm_push_removals_eof_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["keep"], "utf-8", False, quiet=True)
            many = [f"word{i}" for i in range(60)]
            write_text_words(dict_path, ["keep", *many], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            limit_patch = "spell_sync.command_helpers.push_max_removals_without_confirm"
            with (
                patch(limit_patch, return_value=50),
                patch("builtins.input", side_effect=EOFError),
                patch.object(commands.sys, "stdin") as stdin,
            ):
                stdin.isatty.return_value = True
                self.assertIsNone(command_helpers.confirm_push_removals(run, DEFAULT_OPTS))

    def test_confirm_push_removals_yes_skips_prompt(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["keep"], "utf-8", False, quiet=True)
            many = [f"word{i}" for i in range(60)]
            write_text_words(dict_path, ["keep", *many], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            limit_patch = "spell_sync.command_helpers.push_max_removals_without_confirm"
            with patch(limit_patch, return_value=50):
                self.assertTrue(command_helpers.confirm_push_removals(run, CliOptions(yes=True)))

    def test_cmd_push_cancelled_on_removal_reject(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            with (
                patch.object(commands, "_running_apps_check_for_push", return_value=True),
                patch.object(commands, "confirm_push_removals", return_value=False),
                patch.object(commands, "sync_run_for", return_value=run),
                patch.object(commands.sys, "stdin") as stdin,
            ):
                stdin.isatty.return_value = True
                code = commands.cmd_push(CliOptions(wordlist=wordlist))
            self.assertEqual(code, int(ExitCode.CANCELLED))

    def test_before_push_checks_chains_browser_and_removals(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            with (
                patch.object(commands, "_running_apps_check_for_push", return_value=True),
                patch.object(commands, "confirm_push_removals", return_value=True) as removals,
            ):
                self.assertTrue(commands._before_push_checks(run, DEFAULT_OPTS))
                removals.assert_called_once()


class TestLintCaseDedupe(unittest.TestCase):
    def test_merge_case_duplicates_skips_junk(self):
        from spell_sync.words import merge_case_duplicates

        self.assertEqual(merge_case_duplicates(["Alpha", " ", "alpha", "!!!"]), ["Alpha"])

    def test_lint_fix_merges_case_duplicates(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "wordlist.txt")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("Alpha\nalpha\nbeta\n")
            lint_mod.run_lint(path, fix=True)
            words = read_text_words(path, quiet=True)
            self.assertEqual(words, {"Alpha", "beta"})

    def test_pull_save_wordlist_merges_case_duplicates(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["Alpha"], "utf-8", False, quiet=True)
            write_text_words(dict_path, ["alpha", "beta"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            result = run.pull_into_wordlist()
            self.assertEqual(result, (1, 2))
            words = read_text_words(wordlist, quiet=True)
            self.assertEqual(words, {"Alpha", "beta"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
