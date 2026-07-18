"""Tests for TUI launch entry point."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from spell_sync.cli_options import CliOptions
from spell_sync.tui.app import SpellSyncApp, run_app
from spell_sync.tui.controller import TuiController
from spell_sync.tui.launch import cmd_ui
from tests.tui.fake_service import fake_service


class TestLaunch(unittest.TestCase):
    def test_cmd_ui_delegates_to_run_app(self):
        with patch("spell_sync.tui.launch.run_app", return_value=0) as run_app_fn:
            code = cmd_ui(CliOptions())
        run_app_fn.assert_called_once()
        controller = run_app_fn.call_args.args[0]
        self.assertIsInstance(controller, TuiController)
        self.assertEqual(code, 0)

    def test_cmd_ui_logs_and_returns_one_on_failure(self):
        with patch("spell_sync.tui.launch.run_app", side_effect=RuntimeError("boom")):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cmd_ui(CliOptions())
        self.assertEqual(code, 1)
        self.assertIn("TUI failed to start", buf.getvalue())

    def test_run_app_starts_textual_app(self):
        controller = TuiController(fake_service(), CliOptions())
        with patch.object(SpellSyncApp, "run") as run_method:
            code = run_app(controller)
        run_method.assert_called_once()
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
