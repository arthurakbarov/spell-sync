#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Platform and I/O edge-case tests (guards, dry-run backup, CLI branches)."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import spell_sync.app_process_check as guard_mod
import spell_sync.cli as cli_mod
import spell_sync.command_helpers as command_helpers
import spell_sync.dictionaries as dict_mod
import spell_sync.doctor as doctor_mod
import spell_sync.health.report as report_mod
import spell_sync.io as io_mod
import spell_sync.lint as lint_mod
import spell_sync.push_transaction as push_tx_mod
from spell_sync.exit_codes import ExitCode
from spell_sync.sync_run import PushResult, SyncRun


class TestAppProcessEdgePlatforms(unittest.TestCase):
    def test_is_edge_running_windows(self):
        with (
            patch.object(guard_mod, "is_windows", return_value=True),
            patch.object(guard_mod, "_windows_exe_running", return_value=True),
        ):
            self.assertTrue(guard_mod.is_edge_running())

    def test_is_edge_running_macos(self):
        with (
            patch.object(guard_mod, "is_windows", return_value=False),
            patch.object(guard_mod, "sys") as mock_sys,
            patch.object(guard_mod, "_macos_pgrep_exact", return_value=True),
        ):
            mock_sys.platform = "darwin"
            self.assertTrue(guard_mod.is_edge_running())

    def test_is_edge_running_linux(self):
        with (
            patch.object(guard_mod, "is_windows", return_value=False),
            patch.object(guard_mod, "sys") as mock_sys,
            patch.object(guard_mod, "_linux_pgrep_first_resolved", return_value=True),
        ):
            mock_sys.platform = "linux"
            self.assertTrue(guard_mod.is_edge_running())


class TestPushTransactionPlanBackup(unittest.TestCase):
    def test_plan_backup_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "missing.txt"
            temp_dir = Path(d) / "tmp"
            snap = push_tx_mod._plan_backup_path(path, temp_dir)
            self.assertFalse(snap.existed_before)
            self.assertIsNone(snap.backup)

    def test_plan_backup_unreadable_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "dict.txt"
            path.write_text("live\n", encoding="utf-8")
            temp_dir = Path(d) / "tmp"
            with patch.object(push_tx_mod, "is_path_readable", return_value=False):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    snap = push_tx_mod._plan_backup_path(path, temp_dir)
            self.assertIsNone(snap.backup)
            self.assertIn("backup skipped", buf.getvalue())


class TestCliMainBranches(unittest.TestCase):
    def test_main_unknown_command_json_unit(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli_mod.main(["spell-sync", "nope-cmd", "--json"])
        self.assertEqual(code, int(ExitCode.UNKNOWN_COMMAND))
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["command"], "cli")
        self.assertEqual(payload["error"], "unknown_command")


class TestCommandHelpersFormat(unittest.TestCase):
    def test_format_push_done_skipped_name_without_reason(self):
        result = PushResult(
            1,
            ("ok",),
            ("mystery",),
            skipped_reasons={"other": "blocked_by_user"},
        )
        message = command_helpers.format_push_done(result)
        self.assertIn("mystery", message)
        self.assertNotIn("blocked_by_user", message)


class TestDiscoverDictionariesExtras(unittest.TestCase):
    def test_discover_includes_edge_and_libreoffice(self):
        edge_custom = Path("/tmp/edge/Default/Custom Dictionary.txt")
        lo_dict = Path("/tmp/libreoffice/personal.dic")
        with (
            patch("spell_sync.dictionaries.enable_chrome", return_value=False),
            patch("spell_sync.dictionaries.enable_edge", return_value=True),
            patch("spell_sync.dictionaries.enable_editors", return_value=False),
            patch("spell_sync.dictionaries.enable_firefox", return_value=False),
            patch("spell_sync.dictionaries.enable_neovim", return_value=False),
            patch("spell_sync.dictionaries.enable_jetbrains", return_value=False),
            patch("spell_sync.dictionaries.enable_hunspell", return_value=False),
            patch("spell_sync.dictionaries.enable_obsidian", return_value=False),
            patch("spell_sync.dictionaries.enable_brave", return_value=False),
            patch("spell_sync.dictionaries.enable_vivaldi", return_value=False),
            patch("spell_sync.dictionaries.enable_libreoffice", return_value=True),
            patch(
                "spell_sync.dictionaries.edge_dict_paths",
                return_value=[("Default", edge_custom)],
            ),
            patch(
                "spell_sync.dictionaries.libreoffice_dict_paths",
                return_value=[("personal", lo_dict)],
            ),
        ):
            names = {d.name for d in dict_mod.discover_dictionaries()}
        self.assertIn("edge:Default", names)
        self.assertIn("libreoffice:personal", names)


class TestDoctorConfigAndEdge(unittest.TestCase):
    def test_doctor_reports_config_issues_and_edge_running(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            run = SyncRun(wordlist=str(wordlist), dictionaries=[])
        with (
            patch.object(
                report_mod,
                "load_user_settings_with_issues",
                return_value=({"dictionaries": {}}, ["bad line"]),
            ),
            patch.object(
                report_mod,
                "unknown_config_keys",
                return_value=["[weird]: unknown section"],
            ),
            patch.object(report_mod, "edge_dictionaries_enabled", return_value=True),
            patch.object(report_mod, "is_edge_running", return_value=True),
            patch.object(report_mod, "chrome_dictionaries_enabled", return_value=False),
            patch.object(report_mod, "firefox_dictionaries_enabled", return_value=False),
            patch.object(report_mod, "obsidian_dictionaries_enabled", return_value=False),
        ):
            report = doctor_mod.build_doctor_report(run)
        messages = [c.message for c in report.checks]
        self.assertTrue(any("config: bad line" in m for m in messages))
        self.assertTrue(any("unknown section" in m for m in messages))
        self.assertTrue(any("Edge is running" in m for m in messages))


class TestIoEdgeCases(unittest.TestCase):
    def test_warn_write_failed_emits_message(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            io_mod._warn_write_failed("/tmp/x", OSError("denied"), quiet=False)
        self.assertIn("no write access", buf.getvalue())

    def test_warn_write_failed_skipped_when_quiet(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            io_mod._warn_write_failed("/tmp/x", OSError("denied"), quiet=True)
        self.assertEqual(buf.getvalue(), "")

    def test_create_bak_backup_missing_file_returns_true(self):
        with tempfile.TemporaryDirectory() as d:
            missing = Path(d) / "missing.txt"
            self.assertTrue(io_mod.create_bak_backup(missing))

    def test_read_jetbrains_invalid_xml_warns_when_not_quiet(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cachedDictionary.xml"
            path.write_text("<not-xml", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                words = io_mod.read_jetbrains_words(path, quiet=False)
            self.assertEqual(words, set())
            self.assertIn("parse error", buf.getvalue())

    def test_warn_jetbrains_skipped_when_quiet(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cachedDictionary.xml"
            path.write_text("not xml", encoding="utf-8")
            with patch.object(io_mod.log, "quiet", True):
                words = io_mod.read_jetbrains_words(path, quiet=False)
            self.assertEqual(words, set())


class TestLintWhitelist(unittest.TestCase):
    def tearDown(self):
        lint_mod._whitelist_cache = None

    def test_get_lint_whitelist_uses_bundled_when_missing(self):
        lint_mod._whitelist_cache = None
        with patch.object(lint_mod, "project_root", return_value=Path("/no/such/root")):
            words = lint_mod.get_lint_whitelist()
        self.assertIsInstance(words, set)

    def test_get_lint_whitelist_read_oserror(self):
        lint_mod._whitelist_cache = None
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            whitelist = root / "lint-whitelist.txt"
            whitelist.write_text("alpha\n", encoding="utf-8")
            with (
                patch.object(lint_mod, "project_root", return_value=root),
                patch.object(Path, "read_text", side_effect=OSError("denied")),
            ):
                words = lint_mod.get_lint_whitelist()
            self.assertEqual(words, set())


class TestSyncRunImportAddFrom(unittest.TestCase):
    def test_pull_add_from_wordlist_unreadable(self):
        run = SyncRun(wordlist="/tmp/x", dictionaries=[])
        with patch.object(
            run,
            "check_wordlist",
            return_value=ExitCode.WORDLIST_UNREADABLE,
        ):
            result = run.pull_add_from("/tmp/source.txt")
        self.assertEqual(result, ExitCode.WORDLIST_UNREADABLE)

    def test_pull_add_from_missing_source(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            Path(wordlist).write_text("alpha\n", encoding="utf-8")
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            result = run.pull_add_from(os.path.join(d, "missing.txt"))
        self.assertEqual(result, ExitCode.PUSH_ABORT)

    def test_pull_add_from_hunspell_dic(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            source = os.path.join(d, "extra.dic")
            Path(wordlist).write_text("alpha\n", encoding="utf-8")
            Path(source).write_text("beta\n", encoding="utf-8")
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            result = run.pull_add_from(source)
        assert isinstance(result, tuple)
        self.assertEqual(result, (1, 2))

    def test_pull_add_from_write_failure(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            source = os.path.join(d, "extra.txt")
            Path(wordlist).write_text("alpha\n", encoding="utf-8")
            Path(source).write_text("beta\n", encoding="utf-8")
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            with patch.object(run, "_write_wordlist", return_value=False):
                result = run.pull_add_from(source)
        self.assertEqual(result, ExitCode.PUSH_ABORT)
