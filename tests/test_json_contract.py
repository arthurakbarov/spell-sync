#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JSON output contract: always includes `command` and `exit`."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import spell_sync.commands as commands
import spell_sync.doctor as doctor_mod
import spell_sync.plan_cmd as plan_mod
from spell_sync.cli_options import CliOptions
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import write_text_words
from spell_sync.sync_run import SyncRun


class TestJsonContract(unittest.TestCase):
    def _assert_has_exit(self, payload: dict[str, object]) -> None:
        self.assertIn("command", payload)
        self.assertIn("exit", payload)
        self.assertIn("schema_version", payload)
        self.assertEqual(payload["schema_version"], 1)

    def test_status_json_has_exit(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = commands.cmd_status(CliOptions(json_output=True))
        self.assertEqual(code, 0)
        self._assert_has_exit(json.loads(buf.getvalue()))

    def test_status_json_is_pure_with_corrupt_jetbrains_dictionary(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            with open(wordlist, "w", encoding="utf-8") as handle:
                handle.write("alpha\n")
            bad_xml = os.path.join(d, "cachedDictionary.xml")
            with open(bad_xml, "w", encoding="utf-8") as handle:
                handle.write("not xml")
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[
                    Dictionary(
                        "jetbrains:IDEA",
                        bad_xml,
                        DictionaryFormat.JETBRAINS,
                    )
                ],
            )
            buf = io.StringIO()
            with (
                patch.object(commands, "sync_run_for", return_value=run),
                redirect_stdout(buf),
            ):
                code = commands.cmd_status(CliOptions(json_output=True, wordlist=wordlist))
            self.assertEqual(code, 0)
            out = buf.getvalue()
            self.assertTrue(out.lstrip().startswith("{"))
            self._assert_has_exit(json.loads(out))

    def test_doctor_json_has_exit(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            with open(wordlist, "w", encoding="utf-8") as handle:
                handle.write("alpha\n")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = doctor_mod.cmd_doctor(CliOptions(json_output=True, wordlist=wordlist))
            self.assertIn(code, (0, 1))
            self._assert_has_exit(json.loads(buf.getvalue()))

    def test_doctor_check_json_has_health_fields(self):
        import spell_sync.health.report as report_mod

        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            with open(wordlist, "w", encoding="utf-8") as handle:
                handle.write("alpha\n")
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            buf = io.StringIO()
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
                redirect_stdout(buf),
            ):
                code = doctor_mod.cmd_doctor(
                    CliOptions(json_output=True, health_check=True, wordlist=wordlist),
                )
            self.assertEqual(code, int(ExitCode.OK))
            payload = json.loads(buf.getvalue())
            self._assert_has_exit(payload)
            self.assertTrue(payload["ok"])
            self.assertIn("action_count", payload)
            self.assertIn("required_action_count", payload)
            self.assertIn("actions", payload)

    def test_doctor_targets_json_has_exit(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            with open(wordlist, "w", encoding="utf-8") as handle:
                handle.write("alpha\n")
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            buf = io.StringIO()
            with (
                patch.object(doctor_mod, "sync_run_for", return_value=run),
                redirect_stdout(buf),
            ):
                code = doctor_mod.cmd_doctor(
                    CliOptions(json_output=True, show_targets=True, wordlist=wordlist),
                )
            self.assertEqual(code, 0)
            payload = json.loads(buf.getvalue())
            self._assert_has_exit(payload)
            self.assertTrue(payload["targets"])

    def test_lint_json_has_exit(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            with open(wordlist, "w", encoding="utf-8") as handle:
                handle.write("alpha\n")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = commands.cmd_lint(CliOptions(json_output=True, wordlist=wordlist))
            self.assertIn(code, (0, 2))
            out = buf.getvalue()
            self.assertTrue(out.lstrip().startswith("{"))
            self._assert_has_exit(json.loads(out))

    def test_plan_removals_json_is_pure(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            with open(wordlist, "w", encoding="utf-8") as handle:
                handle.write("alpha\n")
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            buf = io.StringIO()
            with (
                patch.object(plan_mod, "sync_run_for", return_value=run),
                redirect_stdout(buf),
            ):
                code = plan_mod.cmd_plan(
                    CliOptions(json_output=True, plan_removals=True, wordlist=wordlist),
                )
            self.assertEqual(code, 0)
            out = buf.getvalue()
            self.assertTrue(out.lstrip().startswith("{"))
            payload = json.loads(out)
            self._assert_has_exit(payload)
            self.assertEqual(payload["command"], "plan")
            self.assertTrue(payload["removals"])

    def test_push_cancel_json_is_pure(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", os.path.join(d, "a.txt"), DictionaryFormat.TEXT)],
            )
            buf = io.StringIO()
            with (
                patch.object(commands, "sync_run_for", return_value=run),
                patch.object(commands, "warn_missing_optional_apps"),
                patch.object(commands, "_running_apps_check_for_push", return_value=False),
                redirect_stdout(buf),
            ):
                code = commands.cmd_push(CliOptions(json_output=True, wordlist=wordlist))
            self.assertEqual(code, int(ExitCode.CANCELLED))
            out = buf.getvalue()
            self.assertTrue(out.lstrip().startswith("{"))
            payload = json.loads(out)
            self._assert_has_exit(payload)
            self.assertEqual(payload["command"], "push")
            self.assertEqual(payload["exit"], int(ExitCode.CANCELLED))
            self.assertEqual(payload["action"], "cancelled")
            self.assertEqual(payload["reason"], "running_apps_check")

    def test_push_json_does_not_prompt_in_tty(self):
        run = SyncRun(wordlist="/tmp/x", dictionaries=[])
        run.push_from_wordlist = lambda **_: ExitCode.OK  # type: ignore[method-assign, assignment]
        buf = io.StringIO()
        with (
            patch.object(commands, "sync_run_for", return_value=run),
            patch.object(commands, "warn_missing_optional_apps"),
            patch.object(commands.sys, "stdin") as stdin,
            patch("builtins.input", side_effect=AssertionError("must not prompt")),
            redirect_stdout(buf),
        ):
            stdin.isatty.return_value = True
            code = commands.cmd_push(CliOptions(json_output=True, review_removals=True))
        self.assertIn(code, (0, 1, 4, 130))


class TestJsonContractExtended(unittest.TestCase):
    def _assert_json_stdout(self, buf: io.StringIO) -> dict[str, object]:
        out = buf.getvalue()
        self.assertTrue(out.lstrip().startswith("{"))
        payload = json.loads(out)
        self.assertIn("command", payload)
        self.assertIn("exit", payload)
        return payload

    def test_init_json_has_exit(self):
        buf = io.StringIO()
        with (
            patch.object(commands, "init_project_directory", return_value=["wordlist.txt"]),
            redirect_stdout(buf),
        ):
            code = commands.cmd_init(CliOptions(json_output=True))
        self.assertEqual(code, 0)
        payload = self._assert_json_stdout(buf)
        self.assertEqual(payload["command"], "init")

    def test_pull_json_has_exit(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            with open(wordlist, "w", encoding="utf-8") as handle:
                handle.write("alpha\n")
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            buf = io.StringIO()
            with (
                patch.object(commands, "sync_run_for", return_value=run),
                redirect_stdout(buf),
            ):
                code = commands.cmd_pull(CliOptions(json_output=True, wordlist=wordlist))
            self.assertEqual(code, 0)
            payload = self._assert_json_stdout(buf)
            self.assertEqual(payload["command"], "pull")


if __name__ == "__main__":
    unittest.main(verbosity=2)
