"""Tests for TUI launch routing."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import spell_sync.cli as cli_mod
from spell_sync.tui.routing import (
    print_non_interactive_ui_error,
    print_non_interactive_usage_error,
    should_launch_tui,
)


class TestShouldLaunchTui(unittest.TestCase):
    def test_no_command_tty(self):
        self.assertTrue(
            should_launch_tui(
                None,
                stdin_is_tty=True,
                stdout_is_tty=True,
                json_requested=False,
            )
        )

    def test_no_command_non_tty(self):
        self.assertFalse(
            should_launch_tui(
                None,
                stdin_is_tty=False,
                stdout_is_tty=True,
                json_requested=False,
            )
        )

    def test_explicit_ui_requires_tty(self):
        self.assertFalse(
            should_launch_tui(
                "ui",
                stdin_is_tty=False,
                stdout_is_tty=False,
                json_requested=False,
            )
        )

    def test_explicit_ui_with_tty(self):
        self.assertTrue(
            should_launch_tui(
                "ui",
                stdin_is_tty=True,
                stdout_is_tty=True,
                json_requested=False,
            )
        )

    def test_json_blocks_tui(self):
        self.assertFalse(
            should_launch_tui(
                None,
                stdin_is_tty=True,
                stdout_is_tty=True,
                json_requested=True,
            )
        )

    def test_other_command(self):
        self.assertFalse(
            should_launch_tui(
                "status",
                stdin_is_tty=True,
                stdout_is_tty=True,
                json_requested=False,
            )
        )


class TestCliRoutingContract(unittest.TestCase):
    def test_no_arg_tty_launches_ui(self):
        with (
            patch.object(cli_mod.sys.stdin, "isatty", lambda: True),
            patch.object(cli_mod.sys.stdout, "isatty", lambda: True),
            patch.object(cli_mod, "cmd_ui", return_value=0) as cmd_ui,
        ):
            code = cli_mod.main(["spell-sync"])
        cmd_ui.assert_called_once()
        self.assertEqual(code, 0)

    def test_no_arg_non_tty_usage_error(self):
        with (
            patch.object(cli_mod.sys.stdin, "isatty", return_value=False),
            patch.object(cli_mod.sys.stdout, "isatty", return_value=False),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli_mod.main(["spell-sync"])
        self.assertEqual(code, 2)
        self.assertIn("requires a command", buf.getvalue())

    def test_ui_tty_launches_ui(self):
        with (
            patch.object(cli_mod.sys.stdin, "isatty", lambda: True),
            patch.object(cli_mod.sys.stdout, "isatty", lambda: True),
            patch.object(cli_mod, "cmd_ui", return_value=0) as cmd_ui,
        ):
            with patch.dict(cli_mod.COMMANDS, {"ui": cmd_ui}):
                code = cli_mod.main(["spell-sync", "ui"])
        cmd_ui.assert_called_once()
        self.assertEqual(code, 0)

    def test_ui_non_tty_controlled_error(self):
        with (
            patch.object(cli_mod.sys.stdin, "isatty", return_value=False),
            patch.object(cli_mod.sys.stdout, "isatty", return_value=False),
            patch.object(cli_mod, "cmd_ui") as cmd_ui,
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli_mod.main(["spell-sync", "ui"])
        cmd_ui.assert_not_called()
        self.assertEqual(code, 2)
        self.assertIn("interactive terminal", buf.getvalue())

    def test_ui_json_parser_error(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli_mod.main(["spell-sync", "ui", "--json"])
        self.assertEqual(code, 2)
        self.assertIn("--json", buf.getvalue())

    def test_help_does_not_launch_ui(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli_mod.main(["spell-sync", "--help"])
        self.assertEqual(code, 0)
        self.assertIn("ui", buf.getvalue())

    def test_status_json_does_not_launch_ui(self):
        with patch.object(cli_mod, "cmd_ui") as cmd_ui:
            with patch.object(cli_mod, "cmd_status", return_value=0) as cmd_status:
                with patch.dict(cli_mod.COMMANDS, {"status": cmd_status}):
                    code = cli_mod.main(["spell-sync", "status", "--json"])
        cmd_ui.assert_not_called()
        cmd_status.assert_called_once()
        self.assertEqual(code, 0)

    def test_print_non_interactive_usage_error(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            print_non_interactive_usage_error()
        self.assertIn("requires a command", buf.getvalue())

    def test_print_non_interactive_ui_error(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            print_non_interactive_ui_error()
        self.assertIn("interactive terminal", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
