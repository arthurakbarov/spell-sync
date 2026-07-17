#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Push safety edge cases: locks, corrupt targets, destructive guards."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import spell_sync.commands as commands
from spell_sync.cli_options import CliOptions
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import write_text_words
from spell_sync.operation_lock import (
    OperationLocked,
    OperationLockInfo,
    lock_path_for_wordlist,
)
from spell_sync.read_outcome import ReadStatus, dictionary_read_result
from spell_sync.skip_reasons import PushSkipReason
from spell_sync.sync_run import PushResult, SyncRun


def _locked_patch(wordlist: Path):
    info = OperationLockInfo(99, "2026-01-01T00:00:00+00:00", "push", str(wordlist))
    lock_path = lock_path_for_wordlist(wordlist)
    return patch(
        "spell_sync.command_helpers.acquire_operation_lock",
        side_effect=OperationLocked(info, lock_path),
    )


class TestMutatingCommandLocks(unittest.TestCase):
    def test_pull_returns_lock_exit(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            with _locked_patch(wordlist):
                code = commands.cmd_pull(CliOptions(wordlist=str(wordlist)))
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))

    def test_push_returns_lock_exit(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            with _locked_patch(wordlist):
                code = commands.cmd_push(CliOptions(wordlist=str(wordlist), yes=True))
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))

    def test_lint_fix_returns_lock_exit(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            with _locked_patch(wordlist):
                code = commands.cmd_lint(CliOptions(wordlist=str(wordlist), fix=True))
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))


class TestPushSafetyEdges(unittest.TestCase):
    def test_push_succeeds_without_configured_dictionaries(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            result = run.push_from_wordlist()
            self.assertIsInstance(result, PushResult)
            assert not isinstance(result, ExitCode)
            self.assertEqual(result.written, ())

    def test_push_partial_when_every_dictionary_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(dict_path, ["beta"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            result = run.push_from_wordlist(skip_names=frozenset({"a"}))
            self.assertIsInstance(result, PushResult)
            assert not isinstance(result, ExitCode)
            self.assertEqual(result.skipped, ("a",))
            self.assertEqual(result.skipped_reasons["a"], PushSkipReason.BLOCKED_BY_USER)

    def test_lint_fix_runs_under_lock(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            with patch("spell_sync.commands.run_lint", return_value=ExitCode.OK) as run_lint:
                code = commands.cmd_lint(CliOptions(wordlist=str(wordlist), fix=True))
            self.assertEqual(code, int(ExitCode.OK))
            run_lint.assert_called_once()

    def test_text_detect_encoding_none(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "words.txt"
            path.write_bytes(b"\x00\x01")
            dictionary = Dictionary("a", str(path), DictionaryFormat.TEXT)
            with patch("spell_sync.read_outcome.detect_encoding_from_bytes", return_value=None):
                self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.CORRUPT)

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "words.txt"
            path.write_text("alpha\n", encoding="utf-8")
            dictionary = Dictionary("a", str(path), DictionaryFormat.TEXT)
            with (
                patch("spell_sync.read_outcome.detect_encoding_from_bytes", return_value="utf-8"),
                patch.object(Path, "read_bytes", return_value=b"\xff\xfe invalid"),
            ):
                self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.CORRUPT)

    def test_readable_for_helpers(self):
        from spell_sync.read_outcome import is_readable_for_push, is_readable_for_union

        self.assertTrue(is_readable_for_push(ReadStatus.MISSING))
        self.assertFalse(is_readable_for_push(ReadStatus.CORRUPT))
        self.assertTrue(is_readable_for_union(ReadStatus.EMPTY))
        self.assertFalse(is_readable_for_union(ReadStatus.UNREADABLE))

    def test_json_null_added_words_corrupt(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "prefs.json"
            path.write_text('{"added_words": null}', encoding="utf-8")
            dictionary = Dictionary("sublime", str(path), DictionaryFormat.JSON)
            self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.CORRUPT)

    def test_json_open_oserror(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "prefs.json"
            path.write_text("{}", encoding="utf-8")
            dictionary = Dictionary("sublime", str(path), DictionaryFormat.JSON)
            with patch.object(Path, "read_bytes", side_effect=OSError("nope")):
                self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.UNREADABLE)

    def test_jetbrains_unicode_corrupt(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "dict.xml"
            path.write_bytes(b"\xff\xfe\xfd")
            dictionary = Dictionary(
                "jetbrains:IDEA",
                str(path),
                DictionaryFormat.JETBRAINS,
            )
            self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.CORRUPT)

    def test_text_unicode_error_while_reading(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "words.txt"
            path.write_text("alpha\n", encoding="utf-8")
            dictionary = Dictionary("a", str(path), DictionaryFormat.TEXT)
            with (
                patch("spell_sync.read_outcome.detect_encoding_from_bytes", return_value="utf-8"),
                patch.object(Path, "read_bytes", return_value=b"ok\n\xff"),
            ):
                self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.CORRUPT)

    def test_chrome_format_status(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "chrome.txt"
            path.write_text("alpha\n", encoding="utf-8")
            dictionary = Dictionary("chrome", str(path), DictionaryFormat.CHROME)
            self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.CORRUPT)

    def test_lint_without_fix_skips_lock(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            with patch("spell_sync.commands.run_lint", return_value=ExitCode.OK) as run_lint:
                code = commands.cmd_lint(CliOptions(wordlist=str(wordlist), fix=False))
            self.assertEqual(code, int(ExitCode.OK))
            run_lint.assert_called_once()

    def test_jetbrains_oserror_unreadable(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "dict.xml"
            path.write_text("<application></application>", encoding="utf-8")
            dictionary = Dictionary(
                "jetbrains:IDEA",
                str(path),
                DictionaryFormat.JETBRAINS,
            )
            with patch.object(Path, "read_bytes", side_effect=OSError("nope")):
                self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.UNREADABLE)
