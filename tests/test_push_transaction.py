#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Transactional push tests and missing-app warnings."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from conftest import DEFAULT_OPTS

import spell_sync.commands as commands
import spell_sync.dictionary_hints as hints_mod
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import read_text_words, write_text_words
from spell_sync.sync_run import PushResult, SyncRun


class TestPushTransaction(unittest.TestCase):
    def test_backup_skips_unreadable_file(self):
        from spell_sync.push_transaction import backup_file

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "dict.txt"
            path.write_text("live\n", encoding="utf-8")
            backup_dir = Path(d) / "bak"
            backup_dir.mkdir()
            with patch("spell_sync.push_transaction.is_path_readable", return_value=False):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    snap = backup_file(path, backup_dir)
            self.assertIsNone(snap.backup)
            self.assertTrue(snap.existed_before)
            self.assertIn("backup skipped", buf.getvalue())

    def test_rollback_removes_new_file_without_backup(self):
        from spell_sync.push_transaction import (
            TargetWriteState,
            _FileBackup,
            _rollback_one_backup,
        )

        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "new.txt"
            target.write_text("created\n", encoding="utf-8")
            bak = _FileBackup(target, None, False, "new")
            bak.write_state = TargetWriteState.WRITE_STARTED
            _rollback_one_backup(bak)
            self.assertFalse(target.exists())

    def test_rollback_skips_not_started_targets(self):
        from spell_sync.push_transaction import (
            _FileBackup,
            _rollback_one_backup,
        )

        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "external.txt"
            target.write_text("external-change\n", encoding="utf-8")
            snap = Path(d) / "snap"
            snap.write_text("old\n", encoding="utf-8")
            bak = _FileBackup(target, snap, True, "external")
            _rollback_one_backup(bak)
            self.assertEqual(target.read_text(encoding="utf-8"), "external-change\n")

    def test_rollback_on_partial_dictionary_failure(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            path_a = os.path.join(d, "a.txt")
            path_b = os.path.join(d, "b.txt")
            words = ["alpha", "beta"]
            write_text_words(wordlist, words, "utf-8", False, quiet=True)
            write_text_words(path_a, ["stale-a"], "utf-8", False, quiet=True)
            write_text_words(path_b, ["stale-b"], "utf-8", False, quiet=True)
            dictionaries = [
                Dictionary("a", path_a, DictionaryFormat.TEXT),
                Dictionary("b", path_b, DictionaryFormat.TEXT),
            ]
            run = SyncRun(wordlist=wordlist, dictionaries=dictionaries)

            def flaky_render(path, rendered):
                if Path(path).name == "b.txt":
                    return False
                return True

            with patch("spell_sync.push_prepared.write_rendered", flaky_render):
                result = run.push_from_wordlist()

            self.assertEqual(result, ExitCode.PUSH_ABORT)
            self.assertEqual(
                read_text_words(wordlist, quiet=True),
                {"alpha", "beta"},
            )
            self.assertEqual(
                read_text_words(path_a, quiet=True),
                {"stale-a"},
            )
            self.assertEqual(
                read_text_words(path_b, quiet=True),
                {"stale-b"},
            )


class TestDictionaryWarnings(unittest.TestCase):
    def test_warn_when_editor_fallback(self):
        with (
            patch.object(hints_mod, "editor_uses_fallback", return_value=True),
            patch.object(hints_mod, "sublime_text_installed", return_value=True),
            patch("spell_sync.config.enable_chrome", return_value=False),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                hints_mod.warn_missing_optional_apps()
            self.assertIn("No code editor install found", buf.getvalue())

    def test_cmd_push_warns_missing_apps(self):
        push_result = PushResult(1, ("a",), ())
        with (
            patch.object(commands, "warn_missing_optional_apps") as warn,
            patch.object(commands, "_running_apps_check_for_push", return_value=True),
            patch.object(commands, "confirm_push_removals", return_value=True),
            patch.object(commands, "sync_run_for") as session_cls,
        ):
            session_cls.return_value.push_from_wordlist.return_value = push_result
            with redirect_stdout(io.StringIO()):
                commands.cmd_push(DEFAULT_OPTS)
            warn.assert_called_once()

    def test_warn_sublime_missing(self):
        with (
            patch.object(hints_mod, "sublime_text_installed", return_value=False),
            patch.object(hints_mod, "editor_uses_fallback", return_value=False),
            patch.object(hints_mod, "enable_chrome", return_value=False),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                hints_mod.warn_missing_optional_apps()
            self.assertIn("Sublime Text not found", buf.getvalue())

    def test_warn_chrome_missing(self):
        with (
            patch.object(hints_mod, "sublime_text_installed", return_value=True),
            patch.object(hints_mod, "editor_uses_fallback", return_value=False),
            patch.object(hints_mod, "enable_chrome", return_value=True),
            patch.object(hints_mod, "chrome_dict_paths", return_value=[]),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                hints_mod.warn_missing_optional_apps()
            self.assertIn("Google Chrome not found", buf.getvalue())

    def test_warn_edge_missing(self):
        with (
            patch.object(hints_mod, "sublime_text_installed", return_value=True),
            patch.object(hints_mod, "editor_uses_fallback", return_value=False),
            patch.object(hints_mod, "enable_chrome", return_value=False),
            patch.object(hints_mod, "enable_edge", return_value=True),
            patch.object(hints_mod, "edge_dict_paths", return_value=[]),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                hints_mod.warn_missing_optional_apps()
            self.assertIn("Microsoft Edge not found", buf.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
