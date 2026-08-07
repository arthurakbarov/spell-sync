#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Runtime helper and greenfield coverage gaps."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from service_test_utils import patch_doctor_service, patch_plan_service

import spell_sync.doctor as doctor_mod
import spell_sync.health.types as health_types_mod
import spell_sync.plan_cmd as plan_mod
import spell_sync.removal_review as removal_mod
from spell_sync.application.reports import PushPreview
from spell_sync.cli_options import CliOptions
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
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
from tests.runtime_helpers import make_sync_run


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
        self.assertTrue(export.startswith("export PATH="))

    def test_path_export_quotes_metacharacters(self):
        import shlex

        tricky = Path("/tmp/dir with $HOME and 'quotes'/bin/spell-sync")
        export = path_export_for_script(tricky)
        quoted = shlex.quote(tricky.parent.as_posix())
        self.assertIn(quoted, export)
        self.assertTrue(export.startswith(f"export PATH={quoted}:"))
        # Unquoted interpolation of $HOME must not remain in the bindir segment.
        self.assertNotRegex(export, r'PATH="/tmp/dir with \$HOME')

    def test_cli_shell_command(self):
        with patch("spell_sync.runtime.cli_argv", return_value=["spell-sync"]):
            self.assertEqual(cli_shell_command("pull"), "spell-sync pull")

    def test_cli_argv_when_script_on_path(self):
        with patch("spell_sync.runtime.shutil.which", return_value="/usr/bin/spell-sync"):
            self.assertEqual(cli_argv(), ["/usr/bin/spell-sync"])

    def test_cli_argv_falls_back_to_module(self):
        with patch("spell_sync.runtime.shutil.which", return_value=None):
            self.assertEqual(cli_argv(), [__import__("sys").executable, "-m", "spell_sync"])

    def test_read_pyproject_version_found(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "pyproject.toml"
            path.write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")
            self.assertEqual(read_pyproject_version(path), "1.2.3")

    def test_read_pyproject_version_oserror(self):
        with patch.object(Path, "read_bytes", side_effect=OSError("nope")):
            self.assertIsNone(read_pyproject_version(Path("/x/pyproject.toml")))

    def test_read_pyproject_version_project_not_dict(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "pyproject.toml"
            path.write_text('project = "nope"\n', encoding="utf-8")
            self.assertIsNone(read_pyproject_version(path))

    def test_discover_pip_script_darwin_iterdir_oserror(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            py_lib = home / "Library" / "Python"
            py_lib.mkdir(parents=True)
            real_iterdir = Path.iterdir

            def flaky_iterdir(self: Path):
                if self == py_lib:
                    raise OSError("denied")
                return real_iterdir(self)

            with (
                patch("spell_sync.runtime.sys.platform", "darwin"),
                patch("spell_sync.runtime.shutil.which", return_value=None),
                patch("spell_sync.runtime.Path.home", return_value=home),
                patch.object(Path, "iterdir", flaky_iterdir),
            ):
                self.assertIsNone(discover_pip_script())

    def test_read_pyproject_version_malformed_raises(self):
        import tomllib

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "pyproject.toml"
            path.write_text("version = [\n", encoding="utf-8")
            with self.assertRaises(tomllib.TOMLDecodeError):
                read_pyproject_version(path)

    def test_plan_removals_human_no_removals(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "dict.txt")
            Path(wordlist).write_text("stay\n", encoding="utf-8")
            Path(dict_path).write_text("stay\n", encoding="utf-8")
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

    def test_discover_pip_script_numeric_version_order(self):
        """String sort would prefer 3.9 over 3.12; numeric order must pick 3.12."""
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            python_root = home / "Library" / "Python"
            for ver in ("3.9", "3.11", "3.12", "other", "3.10.1"):
                script = python_root / ver / "bin" / "spell-sync"
                script.parent.mkdir(parents=True)
                script.write_text("#!/bin/sh\n", encoding="utf-8")
            # Non-directory and symlink entries must be ignored.
            (python_root / "3.99").write_text("not-a-dir\n", encoding="utf-8")
            link = python_root / "3.8"
            link.symlink_to(python_root / "3.9")
            with (
                patch("spell_sync.runtime.sys.platform", "darwin"),
                patch("spell_sync.runtime.shutil.which", return_value=None),
                patch("spell_sync.runtime.Path.home", return_value=home),
            ):
                found = discover_pip_script()
            self.assertEqual(found, python_root / "3.12" / "bin" / "spell-sync")

    def test_discover_pip_script_missing_library_python(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            with (
                patch("spell_sync.runtime.sys.platform", "darwin"),
                patch("spell_sync.runtime.shutil.which", return_value=None),
                patch("spell_sync.runtime.Path.home", return_value=home),
            ):
                self.assertIsNone(discover_pip_script())

    def test_read_pyproject_version_missing_line(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "pyproject.toml"
            path.write_text('[project]\nname = "spell-sync"\n', encoding="utf-8")
            self.assertIsNone(read_pyproject_version(path))

    def test_installed_package_version_pyproject_fallback(self):
        from importlib.metadata import PackageNotFoundError

        with (
            patch("spell_sync.runtime.version", side_effect=PackageNotFoundError("spell-sync")),
            patch(
                "spell_sync.runtime.read_pyproject_version",
                return_value="0.2.0",
            ),
        ):
            self.assertEqual(installed_package_version(), "0.2.0")

    def test_installed_package_version_raises_when_unavailable(self):
        from importlib.metadata import PackageNotFoundError

        with (
            patch("spell_sync.runtime.version", side_effect=PackageNotFoundError("spell-sync")),
            patch("spell_sync.runtime.read_pyproject_version", return_value=None),
        ):
            with self.assertRaises(PackageNotFoundError):
                installed_package_version()

    def test_installed_package_version_does_not_mask_other_errors(self):
        with patch("spell_sync.runtime.version", side_effect=RuntimeError("corrupt metadata")):
            with self.assertRaises(RuntimeError):
                installed_package_version()


class TestGreenfieldCoverageGaps(unittest.TestCase):
    def test_push_setup_warns_corrupt_dictionary(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            bad_xml = os.path.join(d, "cachedDictionary.xml")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            Path(bad_xml).write_text("not xml", encoding="utf-8")
            run = make_sync_run(
                wordlist,
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
            code = plan_mod.cmd_plan(
                CliOptions(wordlist=wordlist, plan_removals=True),
            )
            self.assertEqual(code, 0)

    def test_plan_removals_wordlist_error(self):
        preview = PushPreview(
            prepared=None,
            targets=(),
            additions=0,
            removals=0,
            warnings=(),
            created_at="2026-01-01T00:00:00+00:00",
            plan_identifier="blocked",
            targets_to_update=0,
            unchanged=0,
            skipped=(),
            corrupt=(),
            blocked=(),
            wordlist_error=ExitCode.WORDLIST_UNREADABLE,
        )
        with patch_plan_service(load_push_preview=preview):
            code = plan_mod.cmd_plan(CliOptions(plan_removals=True))
        self.assertEqual(code, 6)

    def test_print_removals_helper(self):
        with tempfile.TemporaryDirectory() as d:
            dict_path = os.path.join(d, "dict.txt")
            Path(dict_path).write_text("gone\n", encoding="utf-8")
            wordlist = os.path.join(d, "wordlist.txt")
            Path(wordlist).write_text("stay\n", encoding="utf-8")
            run = make_sync_run(
                wordlist,
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
            package_version="0.2.0",
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
            with patch_doctor_service(load_doctor_report=report):
                code = doctor_mod.cmd_doctor(CliOptions(wordlist=wordlist))
            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
