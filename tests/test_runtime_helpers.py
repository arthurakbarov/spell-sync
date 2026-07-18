#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Runtime helper and greenfield coverage gaps."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import spell_sync.doctor as doctor_mod
import spell_sync.health.types as health_types_mod
import spell_sync.plan_cmd as plan_mod
import spell_sync.removal_review as removal_mod
from spell_sync.cli_options import CliOptions
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.health.types import DoctorAction
from spell_sync.io import write_text_words
from spell_sync.runtime import (
    cli_argv,
    cli_shell_command,
    discover_pip_script,
    installed_package_version,
    path_export_for_script,
    read_pyproject_version,
)
from spell_sync.sync_run import SyncRun


class TestRuntimeHelpers(unittest.TestCase):
    def test_discover_pip_script_when_on_path(self):
        with patch("spell_sync.runtime.shutil.which", return_value="/usr/bin/spell-sync"):
            self.assertIsNone(discover_pip_script())

    def test_discover_pip_script_local_candidate(self):
        with tempfile.TemporaryDirectory() as d:
            local_bin = Path(d) / ".local" / "bin"
            local_bin.mkdir(parents=True)
            script = local_bin / "spell-sync"
            script.write_text("#!/bin/sh\n", encoding="utf-8")
            with (
                patch("spell_sync.runtime.shutil.which", return_value=None),
                patch("spell_sync.runtime.Path.home", return_value=Path(d)),
            ):
                found = discover_pip_script()
            self.assertEqual(found, script)

    def test_path_export_for_script(self):
        export = path_export_for_script(Path("/tmp/py/bin/spell-sync"))
        self.assertIn("/tmp/py/bin", export)

    def test_cli_shell_command(self):
        with patch("spell_sync.runtime.cli_argv", return_value=["spell-sync"]):
            self.assertEqual(cli_shell_command("pull"), "spell-sync pull")

    def test_cli_argv_when_script_on_path(self):
        with patch("spell_sync.runtime.shutil.which", return_value="/usr/bin/spell-sync"):
            self.assertEqual(cli_argv(), ["/usr/bin/spell-sync"])

    def test_read_pyproject_version_oserror(self):
        with patch.object(Path, "read_text", side_effect=OSError("nope")):
            self.assertIsNone(read_pyproject_version(Path("/x/pyproject.toml")))

    def test_plan_removals_human_no_removals(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "dict.txt")
            Path(wordlist).write_text("stay\n", encoding="utf-8")
            Path(dict_path).write_text("stay\n", encoding="utf-8")
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            with patch.object(plan_mod, "sync_run_for", return_value=run):
                code = plan_mod.cmd_plan(
                    CliOptions(wordlist=wordlist, plan_removals=True),
                )
            self.assertEqual(code, 0)

    def test_discover_pip_script_darwin_library_python(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            py_lib = home / "Library" / "Python" / "3.11"
            script = py_lib / "bin" / "spell-sync"
            script.parent.mkdir(parents=True)
            script.write_text("#!/bin/sh\n", encoding="utf-8")
            with (
                patch("spell_sync.runtime.sys.platform", "darwin"),
                patch("spell_sync.runtime.shutil.which", return_value=None),
                patch("spell_sync.runtime.Path.home", return_value=home),
            ):
                self.assertEqual(discover_pip_script(), script)

    def test_read_pyproject_version_missing_line(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "pyproject.toml"
            path.write_text('[project]\nname = "spell-sync"\n', encoding="utf-8")
            self.assertIsNone(read_pyproject_version(path))

    def test_installed_package_version_pyproject_fallback(self):
        with (
            patch("spell_sync.runtime.version", side_effect=Exception("no dist")),
            patch(
                "spell_sync.runtime.read_pyproject_version",
                return_value="0.1.0",
            ),
        ):
            self.assertEqual(installed_package_version(), "0.1.0")

    def test_installed_package_version_raises_when_unavailable(self):
        with (
            patch("spell_sync.runtime.version", side_effect=Exception("no dist")),
            patch("spell_sync.runtime.read_pyproject_version", return_value=None),
        ):
            with self.assertRaises(Exception):
                installed_package_version()


class TestGreenfieldCoverageGaps(unittest.TestCase):
    def test_push_setup_warns_corrupt_dictionary(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            bad_xml = os.path.join(d, "cachedDictionary.xml")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            Path(bad_xml).write_text("not xml", encoding="utf-8")
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[
                    Dictionary("jetbrains:IDEA", bad_xml, DictionaryFormat.JETBRAINS),
                ],
            )
            result = run.plan_push()
            self.assertIsNotNone(result)

    def test_jetbrains_xml_without_words_element(self):
        import spell_sync.io as io_mod

        xml = """<?xml version="1.0"?>
<application><component name="CachedDictionaryState"></component></application>"""
        words, component, parsed = io_mod._jetbrains_words_from_xml(xml)
        self.assertFalse(parsed)
        self.assertEqual(words, set())

    def test_read_jetbrains_logs_success(self):
        import spell_sync.io as io_mod

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cachedDictionary.xml"
            path.write_text(
                '<?xml version="1.0"?><application><component name="CachedDictionaryState">'
                "<words><w>alpha</w></words></component></application>",
                encoding="utf-8",
            )
            words = io_mod.read_jetbrains_words(path, quiet=False)
            self.assertIn("alpha", words)

    def test_write_jetbrains_failure_and_success_log(self):
        import spell_sync.io as io_mod

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cachedDictionary.xml"
            blocker = Path(d) / "blocker"
            blocker.write_text("not a directory", encoding="utf-8")
            bad_path = blocker / "nested" / "cachedDictionary.xml"
            self.assertFalse(io_mod.write_jetbrains_words(bad_path, ["a"], quiet=False))
            self.assertTrue(io_mod.write_jetbrains_words(path, ["alpha"], quiet=False))

    def test_jetbrains_config_linux_and_paths(self):
        import spell_sync.paths as paths_mod

        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            base = home / ".config" / "JetBrains" / "IdeaIC2024.1" / "options"
            base.mkdir(parents=True)
            dict_path = base / "cachedDictionary.xml"
            dict_path.write_text("<x/>", encoding="utf-8")
            with (
                patch("spell_sync.paths.is_windows", return_value=False),
                patch("spell_sync.paths.is_macos", return_value=False),
                patch("spell_sync.paths.home_dir", return_value=home),
            ):
                self.assertEqual(
                    str(paths_mod.jetbrains_config_dir()),
                    str(home / ".config" / "JetBrains"),
                )
                pairs = paths_mod.jetbrains_dict_paths()
            self.assertEqual(len(pairs), 1)

    def test_jetbrains_dict_paths_oserror(self):
        import spell_sync.paths as paths_mod

        with tempfile.TemporaryDirectory() as d:
            base = Path(d) / "JetBrains"
            base.mkdir()
            with (
                patch("spell_sync.paths.jetbrains_config_dir", return_value=base),
                patch.object(Path, "iterdir", side_effect=OSError("nope")),
            ):
                self.assertEqual(paths_mod.jetbrains_dict_paths(), [])

    def test_read_jetbrains_missing_and_empty(self):
        import spell_sync.io as io_mod

        self.assertEqual(io_mod.read_jetbrains_words("/no/such.xml", quiet=True), set())
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "empty.xml"
            path.write_text("   \n", encoding="utf-8")
            self.assertEqual(io_mod.read_jetbrains_words(path, quiet=True), set())

    def test_read_jetbrains_parse_error_quiet(self):
        import spell_sync.io as io_mod

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bad.xml"
            path.write_text("not-xml", encoding="utf-8")
            self.assertEqual(io_mod.read_jetbrains_words(path, quiet=True), set())

    def test_jetbrains_component_name_branches(self):
        import spell_sync.io as io_mod

        self.assertEqual(io_mod._jetbrains_component_name("/missing.xml"), "CachedDictionaryState")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "dict.xml"
            path.write_text(
                '<?xml version="1.0"?><application><component name="MyDict">'
                "<words><w>one</w></words></component></application>",
                encoding="utf-8",
            )
            self.assertEqual(io_mod._jetbrains_component_name(path), "MyDict")
            empty_name = Path(d) / "empty-name.xml"
            empty_name.write_text(
                '<?xml version="1.0"?><application><component name="">'
                "<words><w>one</w></words></component></application>",
                encoding="utf-8",
            )
            self.assertEqual(io_mod._jetbrains_component_name(empty_name), "CachedDictionaryState")
            with patch.object(Path, "read_text", side_effect=OSError("nope")):
                self.assertEqual(io_mod._jetbrains_component_name(path), "CachedDictionaryState")
            bad = Path(d) / "bad.xml"
            bad.write_text("not-xml", encoding="utf-8")
            self.assertEqual(io_mod._jetbrains_component_name(bad), "CachedDictionaryState")


class TestPlanRemovalsHuman(unittest.TestCase):
    def test_plan_removals_human_lists_words(self):
        with tempfile.TemporaryDirectory() as d:
            dict_path = os.path.join(d, "dict.txt")
            Path(dict_path).write_text("gone\n", encoding="utf-8")
            wordlist = os.path.join(d, "wordlist.txt")
            Path(wordlist).write_text("stay\n", encoding="utf-8")
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            with patch.object(plan_mod, "sync_run_for", return_value=run):
                code = plan_mod.cmd_plan(
                    CliOptions(wordlist=wordlist, plan_removals=True),
                )
            self.assertEqual(code, 0)

    def test_plan_removals_wordlist_error(self):
        run = SyncRun(wordlist="/tmp/x", dictionaries=[])
        run.check_wordlist = lambda: (
            __import__(  # type: ignore[method-assign, assignment]
                "spell_sync.exit_codes",
                fromlist=["ExitCode"],
            ).ExitCode.WORDLIST_UNREADABLE
        )
        with patch.object(plan_mod, "sync_run_for", return_value=run):
            code = plan_mod.cmd_plan(CliOptions(plan_removals=True))
        self.assertEqual(code, 6)

    def test_print_removals_helper(self):
        with tempfile.TemporaryDirectory() as d:
            dict_path = os.path.join(d, "dict.txt")
            Path(dict_path).write_text("gone\n", encoding="utf-8")
            wordlist = os.path.join(d, "wordlist.txt")
            Path(wordlist).write_text("stay\n", encoding="utf-8")
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            removal_mod.print_removals(removal_mod.list_removals(run))


class TestDoctorActionFormatting(unittest.TestCase):
    def test_format_action_line_command(self):
        line = health_types_mod.format_action_line(
            DoctorAction(id="recover-push", reason="journal", command="spell-sync recover"),
        )
        self.assertIn("spell-sync recover", line)

    def test_doctor_human_shows_command_action(self):
        report = doctor_mod.DoctorReport(
            wordlist_path="/tmp/w.txt",
            wordlist_count=1,
            package_version="0.1.0",
            skipped_unreadable=(),
            git_hooks=None,
            cli=doctor_mod.CliStatus(
                on_path=True,
                argv=("/usr/bin/spell-sync",),
                executable="/usr/bin/spell-sync",
                pip_script=None,
                path_export=None,
            ),
            actions=(
                doctor_mod.DoctorAction(
                    id="recover-push",
                    reason="unfinished journal",
                    command="spell-sync recover",
                ),
            ),
            checks=(),
            dictionaries_total=0,
            dictionaries_readable=0,
            dictionaries_writable=0,
            max_drift_add=0,
            max_drift_remove=0,
        )
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            with patch.object(doctor_mod, "sync_run_for", return_value=run):
                with patch.object(doctor_mod, "build_doctor_report", return_value=report):
                    code = doctor_mod.cmd_doctor(CliOptions(wordlist=wordlist))
            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
