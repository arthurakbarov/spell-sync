#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Running-app TOCTOU guards for non-interactive push."""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from unittest.mock import patch

import spell_sync.app_process_check as guard
import spell_sync.command_helpers as command_helpers
import spell_sync.commands as commands
from spell_sync.cli_options import CliOptions
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import read_text_words, write_text_words
from spell_sync.skip_reasons import PushSkipReason
from spell_sync.sync_run import PushResult, SyncRun


class TestRunningAppGuard(unittest.TestCase):
    def _enter_chrome_running(self, stack: ExitStack) -> None:
        stack.enter_context(
            patch(
                "spell_sync.app_process_check.is_chrome_running",
                return_value=True,
            )
        )
        stack.enter_context(
            patch(
                "spell_sync.app_process_check.chrome_dictionaries_enabled",
                return_value=True,
            )
        )
        stack.enter_context(
            patch(
                "spell_sync.app_process_check.firefox_dictionaries_enabled",
                return_value=False,
            )
        )
        stack.enter_context(
            patch(
                "spell_sync.app_process_check.obsidian_dictionaries_enabled",
                return_value=False,
            )
        )

    def test_running_app_skip_names_chrome_profile(self):
        with ExitStack() as stack:
            self._enter_chrome_running(stack)
            skipped = guard.running_app_skip_names(["chrome:Default", "editor:vscode"])
        self.assertEqual(skipped, frozenset({"chrome:Default"}))

    def test_running_app_skip_empty_when_app_not_running(self):
        with (
            patch("spell_sync.app_process_check.is_chrome_running", return_value=False),
            patch("spell_sync.app_process_check.chrome_dictionaries_enabled", return_value=True),
        ):
            skipped = guard.running_app_skip_names(["chrome:Default"])
        self.assertEqual(skipped, frozenset())

    def test_push_skip_running_only_when_yes(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            chrome_path = os.path.join(d, "chrome.txt")
            other_path = os.path.join(d, "other.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(chrome_path, ["stale"], "utf-8", False, quiet=True)
            write_text_words(other_path, ["stale"], "utf-8", False, quiet=True)
            dictionaries = [
                Dictionary("chrome:Default", chrome_path, DictionaryFormat.TEXT),
                Dictionary("editor:vscode", other_path, DictionaryFormat.TEXT),
            ]
            run = SyncRun(wordlist=wordlist, dictionaries=dictionaries)
            with ExitStack() as stack:
                self._enter_chrome_running(stack)
                stdin = stack.enter_context(patch.object(commands.sys, "stdin"))
                stdin.isatty.return_value = True
                self.assertEqual(
                    command_helpers.push_skip_running_app_dicts(run, CliOptions(yes=False)),
                    frozenset(),
                )
                skip = command_helpers.push_skip_running_app_dicts(run, CliOptions(yes=True))
                self.assertEqual(skip, frozenset())

    def test_cmd_push_yes_skips_running_chrome_dictionary(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            chrome_path = os.path.join(d, "chrome.txt")
            other_path = os.path.join(d, "other.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(chrome_path, ["stale"], "utf-8", False, quiet=True)
            write_text_words(other_path, ["stale"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[
                    Dictionary("chrome:Default", chrome_path, DictionaryFormat.TEXT),
                    Dictionary("editor:vscode", other_path, DictionaryFormat.TEXT),
                ],
            )
            with ExitStack() as stack:
                self._enter_chrome_running(stack)
                stack.enter_context(patch.object(commands, "sync_run_for", return_value=run))
                stdin = stack.enter_context(patch.object(commands.sys, "stdin"))
                stdin.isatty.return_value = True
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = commands.cmd_push(CliOptions(yes=True))
            self.assertEqual(code, int(ExitCode.PARTIAL_PUSH))
            self.assertEqual(read_text_words(chrome_path, quiet=True), {"stale"})
            self.assertEqual(read_text_words(other_path, quiet=True), {"alpha"})
            self.assertIn("Google Chrome is running", buf.getvalue())

    def test_push_skips_chrome_at_write_when_running(self):
        """Late TOCTOU: re-check running apps immediately before each dictionary write."""
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            chrome_path = os.path.join(d, "chrome.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(chrome_path, ["stale"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[
                    Dictionary("chrome:Default", chrome_path, DictionaryFormat.TEXT),
                ],
            )
            with ExitStack() as stack:
                self._enter_chrome_running(stack)
                result = run.push_from_wordlist(skip_names=frozenset())
            self.assertIsInstance(result, PushResult)
            self.assertEqual(read_text_words(chrome_path, quiet=True), {"stale"})
            self.assertIn("chrome:Default", result.skipped)
            self.assertEqual(
                result.skipped_reasons.get("chrome:Default"),
                PushSkipReason.RUNNING_APP,
            )

    def test_running_app_skip_unknown_state(self):
        with (
            patch(
                "spell_sync.app_process_check.is_chrome_running",
                return_value=None,
            ),
            patch(
                "spell_sync.app_process_check.chrome_dictionaries_enabled",
                return_value=True,
            ),
            patch(
                "spell_sync.app_process_check.firefox_dictionaries_enabled",
                return_value=False,
            ),
            patch(
                "spell_sync.app_process_check.obsidian_dictionaries_enabled",
                return_value=False,
            ),
        ):
            skipped = guard.running_app_skip_names(["chrome:Default"])
            self.assertEqual(skipped, frozenset({"chrome:Default"}))

    def test_obsidian_name_match_exact(self):
        with (
            patch(
                "spell_sync.app_process_check.is_obsidian_running",
                return_value=True,
            ),
            patch(
                "spell_sync.app_process_check.obsidian_dictionaries_enabled",
                return_value=True,
            ),
            patch(
                "spell_sync.app_process_check.chrome_dictionaries_enabled",
                return_value=False,
            ),
            patch(
                "spell_sync.app_process_check.firefox_dictionaries_enabled",
                return_value=False,
            ),
        ):
            skipped = guard.running_app_skip_names(["obsidian", "obsidian-extra"])
        self.assertEqual(skipped, frozenset({"obsidian"}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
