#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""doctor, watch, automation, Firefox/Neovim paths."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import spell_sync.doctor as doctor_mod
import spell_sync.health.actions as health_actions_mod
import spell_sync.health.inspect as health_inspect_mod
import spell_sync.health.report as report_mod
import spell_sync.log as log_module
import spell_sync.paths as paths_mod
from spell_sync.cli_options import CliOptions
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import write_text_words
from spell_sync.sync_run import SyncRun


class TestFirefoxNeovimPaths(unittest.TestCase):
    def test_firefox_dict_paths(self):
        with tempfile.TemporaryDirectory() as d:
            profiles = Path(d) / "Profiles"
            profile = profiles / "abc.default-release"
            profile.mkdir(parents=True)
            (profile / "persdict.dat").write_text("firefoxword\n", encoding="utf-8")
            with patch.object(paths_mod, "firefox_profiles_dir", return_value=profiles):
                pairs = paths_mod.firefox_dict_paths()
            self.assertEqual(len(pairs), 1)
            self.assertEqual(pairs[0][1].name, "persdict.dat")

    def test_firefox_skips_profiles_without_persdict(self):
        with tempfile.TemporaryDirectory() as d:
            profiles = Path(d) / "Profiles"
            empty = profiles / "empty.default"
            used = profiles / "used.default-release"
            empty.mkdir(parents=True)
            used.mkdir(parents=True)
            (used / "persdict.dat").write_text("word\n", encoding="utf-8")
            with patch.object(paths_mod, "firefox_profiles_dir", return_value=profiles):
                pairs = paths_mod.firefox_dict_paths()
            self.assertEqual(len(pairs), 1)
            self.assertEqual(pairs[0][0], "used.default-release")

    def test_neovim_dict_paths(self):
        with patch.object(paths_mod, "neovim_data_dir", return_value=Path("/nvim")):
            pairs = paths_mod.neovim_dict_paths()
        self.assertEqual(pairs[0][1], Path("/nvim/site/spell/en.utf-8.add"))

    def test_discover_includes_firefox_when_enabled(self):
        import spell_sync.dictionaries as dict_mod

        with tempfile.TemporaryDirectory() as d:
            profile = Path(d) / "p.default"
            profile.mkdir()
            (profile / "persdict.dat").write_text("w\n", encoding="utf-8")
            with (
                patch.object(dict_mod, "is_windows", return_value=False),
                patch.object(dict_mod, "is_macos", return_value=False),
                patch.object(dict_mod, "enable_chrome", return_value=False),
                patch.object(dict_mod, "enable_editors", return_value=False),
                patch.object(dict_mod, "enable_neovim", return_value=False),
                patch.object(dict_mod, "enable_firefox", return_value=True),
                patch.object(
                    dict_mod,
                    "firefox_dict_paths",
                    return_value=[("p", profile / "persdict.dat")],
                ),
            ):
                names = [item.name for item in dict_mod.discover_dictionaries()]
            self.assertIn("firefox:p", names)


class TestDoctor(unittest.TestCase):
    def test_doctor_ok_with_wordlist(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[],
            )
            report = doctor_mod.build_doctor_report(run)
            self.assertEqual(report.wordlist_count, 1)
            self.assertFalse(report.has_errors)

    def test_doctor_missing_wordlist_error(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            report = doctor_mod.build_doctor_report(run)
            self.assertTrue(report.has_errors)
            self.assertEqual(report.checks[0].level, "error")
            self.assertIn("missing", report.checks[0].message)

    def test_doctor_broken_wordlist_symlink_error(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks not supported")
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            os.symlink("missing-target.txt", wordlist)
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            report = doctor_mod.build_doctor_report(run)
            self.assertTrue(report.has_errors)
            self.assertIn("broken symlink", report.checks[0].message)

    def test_doctor_empty_wordlist_warn(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            Path(wordlist).write_text("", encoding="utf-8")
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            report = doctor_mod.build_doctor_report(run)
            levels = [check.level for check in report.checks]
            self.assertIn("warn", levels)

    def test_doctor_unreadable_dictionary_warn(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            blocked = os.path.join(d, "blocked.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            Path(blocked).write_text("secret\n", encoding="utf-8")
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[
                    Dictionary("blocked", blocked, DictionaryFormat.TEXT),
                ],
            )

            def readable(path):
                target = str(path)
                return target == wordlist or target.endswith("wordlist.txt")

            with (
                patch("spell_sync.health.report.is_path_readable", side_effect=readable),
                patch("spell_sync.read_outcome.is_path_readable", side_effect=readable),
            ):
                report = doctor_mod.build_doctor_report(run)
            warn_msgs = [c.message for c in report.checks if c.level == "warn"]
            self.assertTrue(any("blocked" in msg for msg in warn_msgs))

    def test_doctor_macos_info_when_partial_readable(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[
                    Dictionary("a", os.path.join(d, "a.txt"), DictionaryFormat.TEXT),
                ],
            )

            def readable(path):
                target = str(path)
                return target == wordlist or target.endswith("wordlist.txt")

            with (
                patch.object(report_mod, "is_macos", return_value=True),
                patch("spell_sync.health.report.is_path_readable", side_effect=readable),
                patch("spell_sync.read_outcome.is_path_readable", side_effect=readable),
            ):
                report = doctor_mod.build_doctor_report(run)
            info_msgs = [c.message for c in report.checks if c.level == "info"]
            self.assertTrue(any("Full Disk Access" in msg for msg in info_msgs))

    def test_doctor_macos_applespell_unreadable_warn(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            blocked = os.path.join(d, "LocalDictionary")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            Path(blocked).write_text("secret\n", encoding="utf-8")
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[
                    Dictionary(
                        "macos-applespell",
                        blocked,
                        DictionaryFormat.TEXT,
                    ),
                ],
            )

            def readable(path):
                target = str(path)
                return target == wordlist or target.endswith("wordlist.txt")

            with (
                patch.object(report_mod, "is_macos", return_value=True),
                patch("spell_sync.health.report.is_path_readable", side_effect=readable),
                patch("spell_sync.read_outcome.is_path_readable", side_effect=readable),
            ):
                report = doctor_mod.build_doctor_report(run)
            warn_msgs = [c.message for c in report.checks if c.level == "warn"]
            self.assertTrue(any("macos-applespell unreadable" in msg for msg in warn_msgs))
            self.assertFalse(any("read failed" in msg for msg in warn_msgs))
            self.assertEqual(report.skipped_unreadable, ("macos-applespell",))
            info_msgs = [c.message for c in report.checks if c.level == "info"]
            self.assertFalse(any("if dictionaries stay unreadable" in msg for msg in info_msgs))

    def test_doctor_quiet_status_diffs(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            blocked = os.path.join(d, "blocked.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            Path(blocked).write_text("secret\n", encoding="utf-8")
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[
                    Dictionary("blocked", blocked, DictionaryFormat.TEXT),
                ],
            )

            def readable(path):
                target = str(path)
                return target == wordlist or target.endswith("wordlist.txt")

            buf = io.StringIO()
            log_module.log.quiet = False
            with (
                patch("spell_sync.health.report.is_path_readable", side_effect=readable),
                patch("spell_sync.read_outcome.is_path_readable", side_effect=readable),
                redirect_stdout(buf),
            ):
                doctor_mod.build_doctor_report(run)
            self.assertNotIn("diff skipped", buf.getvalue())

    def test_doctor_includes_package_version(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            report = doctor_mod.build_doctor_report(run)
            self.assertTrue(report.package_version)
            payload = doctor_mod.doctor_payload(report)
            self.assertEqual(payload["version"], report.package_version)

    def test_doctor_cli_not_on_path_info(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            with (
                patch.object(health_inspect_mod.shutil, "which", return_value=None),
                patch.object(health_inspect_mod, "discover_pip_script", return_value=None),
            ):
                report = doctor_mod.build_doctor_report(run)
            self.assertFalse(report.cli.on_path)
            self.assertTrue(
                any("not on PATH" in c.message for c in report.checks if c.level == "info"),
            )
            payload = doctor_mod.doctor_payload(report)
            self.assertFalse(payload["cli"]["on_path"])
            self.assertIn("-m", payload["cli"]["argv"])

    def test_doctor_cli_pip_script_path_export(self):
        pip_script = Path("/tmp/py/bin/spell-sync")
        cli_status = doctor_mod.CliStatus(
            on_path=False,
            argv=("python3", "-m", "spell_sync"),
            executable=None,
            pip_script=str(pip_script),
            path_export='export PATH="/tmp/py/bin:$PATH"',
        )
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            with patch.object(report_mod, "inspect_cli", return_value=cli_status):
                report = doctor_mod.build_doctor_report(run)
            self.assertEqual(report.cli.pip_script, str(pip_script))
            self.assertTrue(
                any("export PATH=" in c.message for c in report.checks if c.level == "info"),
            )
            payload = doctor_mod.doctor_payload(report)
            self.assertEqual(payload["cli"]["path_export"], 'export PATH="/tmp/py/bin:$PATH"')

    def test_doctor_actions_json(self):
        pip_script = Path("/tmp/py/bin/spell-sync")
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            cli_status = doctor_mod.CliStatus(
                on_path=False,
                argv=("python3", "-m", "spell_sync"),
                executable=None,
                pip_script=str(pip_script),
                path_export='export PATH="/tmp/py/bin:$PATH"',
            )
            with (
                patch.object(report_mod, "inspect_cli", return_value=cli_status),
                patch.object(report_mod, "inspect_git_hooks", return_value=None),
            ):
                report = doctor_mod.build_doctor_report(run)
            payload = doctor_mod.doctor_payload(report)
            ids = [item["id"] for item in payload["actions"]]
            self.assertIn("path-export", ids)

    def test_doctor_actions_path_export_shell(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            cli_status = doctor_mod.CliStatus(
                on_path=False,
                argv=("python3", "-m", "spell_sync"),
                executable=None,
                pip_script="/tmp/bin/spell-sync",
                path_export='export PATH="/tmp/bin:$PATH"',
            )
            with (
                patch.object(report_mod, "inspect_cli", return_value=cli_status),
                patch.object(report_mod, "inspect_git_hooks", return_value=None),
            ):
                report = doctor_mod.build_doctor_report(run)
            path_action = next(a for a in report.actions if a.id == "path-export")
            self.assertEqual(path_action.shell, 'export PATH="/tmp/bin:$PATH"')
            self.assertIsNone(path_action.command)

    def test_doctor_check_exits_on_actions(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            err = io.StringIO()
            with (
                patch.object(doctor_mod, "sync_run_for", return_value=run),
                patch.object(
                    report_mod,
                    "inspect_cli",
                    return_value=doctor_mod.CliStatus(
                        on_path=False,
                        argv=("python3", "-m", "spell_sync"),
                        executable=None,
                        pip_script="/tmp/bin/spell-sync",
                        path_export='export PATH="/tmp/bin:$PATH"',
                    ),
                ),
                patch.object(report_mod, "inspect_git_hooks", return_value=None),
                redirect_stderr(err),
            ):
                code = doctor_mod.cmd_doctor(CliOptions(health_check=True))
            self.assertEqual(code, int(ExitCode.LINT_FAILED))
            self.assertIn("path-export", err.getvalue())

    def test_doctor_check_ok_with_only_optional_actions(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            blocked = os.path.join(d, "LocalDictionary")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            Path(blocked).write_text("secret\n", encoding="utf-8")
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[
                    Dictionary(
                        "macos-applespell",
                        blocked,
                        DictionaryFormat.TEXT,
                    ),
                ],
            )
            err = io.StringIO()

            def readable(path):
                target = str(path)
                return target == wordlist or target.endswith("wordlist.txt")

            with (
                patch.object(doctor_mod, "sync_run_for", return_value=run),
                patch.object(report_mod, "is_macos", return_value=True),
                patch.object(health_actions_mod, "is_macos", return_value=True),
                patch("spell_sync.health.report.is_path_readable", side_effect=readable),
                patch("spell_sync.read_outcome.is_path_readable", side_effect=readable),
                patch.object(
                    report_mod,
                    "inspect_cli",
                    return_value=doctor_mod.CliStatus(
                        on_path=True,
                        argv=("/usr/bin/spell-sync",),
                        executable="/usr/bin/spell-sync",
                        pip_script=None,
                        path_export=None,
                    ),
                ),
                patch.object(report_mod, "inspect_git_hooks", return_value=None),
                redirect_stderr(err),
            ):
                code = doctor_mod.cmd_doctor(CliOptions(health_check=True))
            self.assertEqual(code, int(ExitCode.OK))
            self.assertIn("macos-fda", err.getvalue())

    def test_doctor_check_ok_when_clean(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            with (
                patch.object(doctor_mod, "sync_run_for", return_value=run),
                patch.object(
                    report_mod,
                    "inspect_cli",
                    return_value=doctor_mod.CliStatus(
                        on_path=True,
                        argv=("/usr/bin/spell-sync",),
                        executable="/usr/bin/spell-sync",
                        pip_script=None,
                        path_export=None,
                    ),
                ),
                patch.object(report_mod, "inspect_git_hooks", return_value=None),
            ):
                code = doctor_mod.cmd_doctor(CliOptions(health_check=True))
            self.assertEqual(code, int(ExitCode.OK))

    def test_doctor_check_exits_on_errors(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            Path(wordlist).write_text("alpha\n", encoding="utf-8")
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            err = io.StringIO()
            with (
                patch.object(doctor_mod, "sync_run_for", return_value=run),
                patch.object(run, "check_wordlist", return_value=ExitCode.WORDLIST_UNREADABLE),
                patch.object(
                    report_mod,
                    "inspect_cli",
                    return_value=doctor_mod.CliStatus(
                        on_path=True,
                        argv=("/usr/bin/spell-sync",),
                        executable="/usr/bin/spell-sync",
                        pip_script=None,
                        path_export=None,
                    ),
                ),
                patch.object(report_mod, "inspect_git_hooks", return_value=None),
                redirect_stderr(err),
            ):
                code = doctor_mod.cmd_doctor(CliOptions(health_check=True))
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))
            self.assertIn("wordlist unreadable", err.getvalue())

    def test_inspect_git_hooks_not_a_directory(self):
        with tempfile.TemporaryDirectory() as d:
            hooks_path = Path(d) / "hooks-file"
            hooks_path.write_text("not a dir\n", encoding="utf-8")
            self.assertIsNone(health_inspect_mod.inspect_git_hooks(hooks_path))

    def test_inspect_git_hooks_pre_push_read_oserror(self):
        with tempfile.TemporaryDirectory() as d:
            hooks_dir = Path(d) / "hooks"
            hooks_dir.mkdir()
            pre_push = hooks_dir / "pre-push"
            pre_push.write_text("#!/bin/sh\n", encoding="utf-8")
            original_read_text = Path.read_text

            def deny_read(self, *args, **kwargs):
                if self == pre_push:
                    raise OSError("denied")
                return original_read_text(self, *args, **kwargs)

            with patch.object(Path, "read_text", deny_read):
                status = health_inspect_mod.inspect_git_hooks(hooks_dir)
            assert status is not None
            self.assertTrue(status.pre_push)
            self.assertTrue(status.pre_push_stale)

    def test_doctor_chrome_running_warn(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            with (
                patch.object(report_mod, "chrome_dictionaries_enabled", return_value=True),
                patch.object(report_mod, "is_chrome_running", return_value=True),
            ):
                report = doctor_mod.build_doctor_report(run)
            self.assertTrue(
                any("Chrome is running" in c.message for c in report.checks if c.level == "warn"),
            )

    def test_doctor_obsidian_running_warn(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            with (
                patch.object(report_mod, "obsidian_dictionaries_enabled", return_value=True),
                patch.object(report_mod, "is_obsidian_running", return_value=True),
            ):
                report = doctor_mod.build_doctor_report(run)
            self.assertTrue(
                any("Obsidian is running" in c.message for c in report.checks if c.level == "warn"),
            )

    def test_doctor_hooks_missing_info(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            hooks_dir = Path(d) / ".git" / "hooks"
            hooks_dir.mkdir(parents=True)
            report = doctor_mod.build_doctor_report(run)
            self.assertTrue(
                any("Git hooks incomplete" in c.message for c in report.checks),
            )

    def test_doctor_pre_push_stale_warn(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            hooks_dir = Path(d) / ".git" / "hooks"
            hooks_dir.mkdir(parents=True)
            (hooks_dir / "pre-push").write_text(
                'root="$(cd "$(dirname "$0")/.." && pwd)"\n',
                encoding="utf-8",
            )
            (hooks_dir / "pre-commit").write_text("#!/bin/sh\n", encoding="utf-8")
            report = doctor_mod.build_doctor_report(run)
            self.assertTrue(
                any("pre-push hook is outdated" in c.message for c in report.checks),
            )
            self.assertTrue(report.git_hooks is not None)
            self.assertTrue(report.git_hooks.pre_push_stale)

    def test_doctor_git_hooks_json(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            hooks_dir = Path(d) / ".git" / "hooks"
            hooks_dir.mkdir(parents=True)
            report = doctor_mod.build_doctor_report(run)
            payload = doctor_mod.doctor_payload(report)
            self.assertEqual(
                payload["git_hooks"],
                {
                    "pre_push": False,
                    "pre_commit": False,
                    "pre_push_stale": False,
                },
            )

    def test_doctor_destructive_push_risk_warn(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "dict.txt")
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
                dictionaries=[Dictionary("s", dict_path, DictionaryFormat.TEXT)],
            )
            report = doctor_mod.build_doctor_report(run)
            self.assertTrue(
                any("run `pull` first" in c.message for c in report.checks),
            )

    def test_doctor_unreadable_wordlist_error(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            Path(wordlist).write_text("alpha\n", encoding="utf-8")
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            with patch.object(run, "check_wordlist", return_value=ExitCode.WORDLIST_UNREADABLE):
                report = doctor_mod.build_doctor_report(run)
            self.assertTrue(report.has_errors)
            error_msgs = [c.message for c in report.checks if c.level == "error"]
            self.assertTrue(any("wordlist unreadable" in msg for msg in error_msgs))

    def test_doctor_json_missing_wordlist(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            opts = CliOptions(json_output=True, wordlist=wordlist)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = doctor_mod.cmd_doctor(opts)
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))
            payload = json.loads(buf.getvalue())
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["exit"], int(ExitCode.PUSH_ABORT))

    def test_doctor_human_output(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            opts = CliOptions(wordlist=wordlist)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = doctor_mod.cmd_doctor(opts)
            self.assertEqual(code, 0)
            out = buf.getvalue()
            self.assertIn("wordlist:", out)
            self.assertIn("doctor: no blocking issues", out)
            self.assertIn("spell-sync", out)

    def test_doctor_human_output_path_export_shell(self):
        cli_status = doctor_mod.CliStatus(
            on_path=False,
            argv=("python3", "-m", "spell_sync"),
            executable=None,
            pip_script="/tmp/bin/spell-sync",
            path_export='export PATH="/tmp/bin:$PATH"',
        )
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            opts = CliOptions(wordlist=wordlist)
            buf = io.StringIO()
            with (
                patch.object(report_mod, "inspect_cli", return_value=cli_status),
                patch.object(report_mod, "inspect_git_hooks", return_value=None),
                redirect_stdout(buf),
            ):
                code = doctor_mod.cmd_doctor(opts)
            self.assertEqual(code, 0)
            out = buf.getvalue()
            self.assertIn('export PATH="/tmp/bin:$PATH"', out)
            self.assertIn("next steps:", out)

    def test_doctor_human_output_warn_and_hint(self):
        cli_status = doctor_mod.CliStatus(
            on_path=True,
            argv=("/usr/bin/spell-sync",),
            executable="/usr/bin/spell-sync",
            pip_script=None,
            path_export=None,
        )
        report = doctor_mod.DoctorReport(
            wordlist_path="/tmp/w.txt",
            wordlist_count=1,
            package_version="1.0.0",
            skipped_unreadable=(),
            git_hooks=None,
            cli=cli_status,
            actions=(
                doctor_mod.DoctorAction(
                    id="macos-fda",
                    reason="unreadable dictionary",
                    hint="System Settings → Privacy",
                    optional=True,
                ),
            ),
            checks=(doctor_mod.DoctorCheck("warn", "Edge is running"),),
            dictionaries_total=0,
            dictionaries_readable=0,
            dictionaries_writable=0,
            max_drift_add=0,
            max_drift_remove=0,
        )
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            opts = CliOptions(wordlist=wordlist)
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            buf = io.StringIO()
            with (
                patch.object(doctor_mod, "sync_run_for", return_value=run),
                patch.object(doctor_mod, "build_doctor_report", return_value=report),
                redirect_stdout(buf),
            ):
                code = doctor_mod.cmd_doctor(opts)
            self.assertEqual(code, 0)
            out = buf.getvalue()
            self.assertIn("[WARN] Edge is running", out)
            self.assertIn("System Settings", out)
            self.assertIn("next steps:", out)

    def test_doctor_human_output_with_errors(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "missing.txt")
            opts = CliOptions(wordlist=wordlist)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = doctor_mod.cmd_doctor(opts)
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))
            out = buf.getvalue()
            self.assertIn("[ERROR]", out)
            self.assertNotIn("doctor: no blocking issues", out)
