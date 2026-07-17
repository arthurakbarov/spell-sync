#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI smoke tests: parsing, main(), subprocess."""

from __future__ import annotations

import io
import json
import os
import runpy
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import spell_sync.cli as cli_mod
from spell_sync.cli_options import CliOptions
from spell_sync.exit_codes import ExitCode

_ROOT = Path(__file__).resolve().parent.parent


def _run_sync(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "spell_sync", *args],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


class TestParseArgs(unittest.TestCase):
    def test_empty_argv_defaults_to_status(self):
        args = cli_mod._parse_args([])
        self.assertIsNotNone(args)
        assert args is not None
        self.assertEqual(args.command, "status")

    def test_global_flags_before_command_map_to_status(self):
        args = cli_mod._parse_args(["-v"])
        self.assertIsNotNone(args)
        assert args is not None
        self.assertEqual(args.command, "status")
        self.assertTrue(args.verbose)

    def test_unknown_command_returns_none(self):
        self.assertIsNone(cli_mod._parse_args(["nope"]))

    def test_push_dry_run_and_yes(self):
        args = cli_mod._parse_args(["push", "-n", "-y", "-v"])
        self.assertIsNotNone(args)
        assert args is not None
        self.assertEqual(args.command, "push")
        self.assertTrue(args.dry_run)
        self.assertTrue(args.yes)
        self.assertTrue(args.verbose)

    def test_lint_fix_strict_json(self):
        args = cli_mod._parse_args(["lint", "--fix", "--strict", "--json"])
        self.assertIsNotNone(args)
        assert args is not None
        self.assertTrue(args.fix)
        self.assertTrue(args.strict)
        self.assertTrue(args.json_output)


class TestMain(unittest.TestCase):
    def test_json_status_suppresses_human_log(self):
        payload = {"command": "status", "exit": 0, "word_count": 1, "diffs": []}

        def fake_status(opts: CliOptions) -> int:
            from spell_sync.json_output import emit_json

            emit_json(payload)
            return int(ExitCode.OK)

        with patch.dict(cli_mod.COMMANDS, {"status": fake_status}):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli_mod.main(["spell-sync", "status", "--json"])
            out = buf.getvalue()
            self.assertEqual(code, 0)
            self.assertNotIn("[info ]", out)
            parsed = json.loads(out)
            self.assertEqual(parsed["command"], "status")

    def test_all_commands_dispatch_via_main(self):
        for name in cli_mod.COMMANDS:

            def handler(_opts) -> int:
                return 0

            argv = ["spell-sync", name]
            if name == "contains":
                argv.append("testword")
            with patch.dict(cli_mod.COMMANDS, {name: handler}, clear=True):
                with redirect_stdout(io.StringIO()):
                    code = cli_mod.main(argv)
                self.assertEqual(code, 0)

    def test_main_default_argv(self):
        with patch.object(cli_mod, "main", wraps=cli_mod.main) as main_fn:
            with patch.object(cli_mod.sys, "argv", ["spell-sync", "status"]):
                with patch.dict(cli_mod.COMMANDS, {"status": lambda opts: 0}):
                    with redirect_stdout(io.StringIO()):
                        code = cli_mod.main()
            self.assertEqual(code, 0)
            main_fn.assert_called_once()

    def test_entry_point_exits_with_handler_code(self):
        with patch.object(cli_mod, "main", return_value=7):
            with self.assertRaises(SystemExit) as ctx:
                cli_mod.entry_point()
            self.assertEqual(ctx.exception.code, 7)

    def test_main_module_delegates_to_cli_main(self):
        with patch("spell_sync.cli.main", return_value=0) as main_fn:
            with self.assertRaises(SystemExit) as ctx:
                runpy.run_module("spell_sync", run_name="__main__")
            self.assertEqual(ctx.exception.code, 0)
            main_fn.assert_called_once()


class TestSubprocessSmoke(unittest.TestCase):
    def test_main_top_level_help_in_process(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli_mod.main(["spell-sync", "--help"])
        self.assertEqual(code, 0)
        self.assertIn("push", buf.getvalue())
        self.assertIn("pull", buf.getvalue())

    def test_top_level_help(self):
        proc = _run_sync("--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("push", proc.stdout)
        self.assertIn("spell-sync", proc.stdout)

    def test_unknown_command_no_module_docstring(self):
        proc = _run_sync("no-such-cmd")
        self.assertEqual(proc.returncode, int(ExitCode.UNKNOWN_COMMAND))
        combined = proc.stderr + proc.stdout
        self.assertIn("unknown command", combined)
        self.assertNotIn("unified custom spellcheck", combined.lower())

    def test_push_help(self):
        proc = _run_sync("push", "--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("dry-run", proc.stdout)

    def test_unknown_command_exit_code(self):
        proc = _run_sync("no-such-cmd")
        self.assertEqual(proc.returncode, int(ExitCode.UNKNOWN_COMMAND))
        self.assertIn("unknown command", proc.stderr + proc.stdout)

    def test_unknown_command_json_stdout(self):
        proc = _run_sync("no-such-cmd", "--json")
        self.assertEqual(proc.returncode, int(ExitCode.UNKNOWN_COMMAND))
        data = json.loads(proc.stdout)
        self.assertEqual(data["command"], "cli")
        self.assertEqual(data["exit"], int(ExitCode.UNKNOWN_COMMAND))
        self.assertEqual(data["error"], "unknown_command")
        self.assertIn("no-such-cmd", data.get("argv", []))

    def test_status_json_stdout(self):
        proc = _run_sync("status", "--json")
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data["command"], "status")
        self.assertIn("dictionaries", data)
        self.assertNotIn("[info ]", proc.stdout)

    def test_version_subprocess(self):
        proc = _run_sync("version")
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(proc.stdout.strip())

    def test_version_json(self):
        proc = _run_sync("version", "--json")
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data["command"], "version")
        self.assertIn("version", data)

    def test_init_subprocess_in_empty_directory(self):
        with tempfile.TemporaryDirectory() as d:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(_ROOT)
            proc = subprocess.run(
                [sys.executable, "-m", "spell_sync", "init"],
                cwd=d,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            self.assertTrue((Path(d) / "wordlist.txt").is_file())
            self.assertTrue((Path(d) / "spell-sync.toml").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
