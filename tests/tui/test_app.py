"""Headless Textual app tests."""

from __future__ import annotations

import unittest
from importlib import resources
from unittest import mock

from spell_sync.application.reports import StatusSnapshot
from spell_sync.cli_options import CliOptions
from spell_sync.exit_codes import ExitCode
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.dashboard import DashboardScreen
from spell_sync.tui.screens.preview_screen import PreviewScreen
from spell_sync.tui.screens.status_screen import StatusScreen
from tests.tui.fake_service import (
    FakeTuiService,
    fake_service,
    sample_dashboard,
    sample_preview,
    sample_status,
)


class TestSpellSyncApp(unittest.IsolatedAsyncioTestCase):
    async def test_dashboard_mounts(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)
            summary = app.screen.query_one("#dashboard-summary")
            self.assertIn("Spell Sync", str(summary.render()))

    async def test_quit_button_exits(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.click("#btn-quit")
            await pilot.pause()

    async def test_quit_hotkey_exits(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.press("q")
            await pilot.pause()

    async def test_preview_button_opens_preview(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.click("#btn-preview")
            await pilot.pause()
            self.assertIsInstance(app.screen, PreviewScreen)

    async def test_dashboard_refresh_hotkey(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.press("r")
            await pilot.pause()
            summary = app.screen.query_one("#dashboard-summary")
            self.assertIn("Spell Sync", str(summary.render()))

    async def test_dashboard_wordlist_error_health(self):
        controller = TuiController(
            fake_service(wordlist_error=ExitCode.PUSH_ABORT),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            summary = app.screen.query_one("#dashboard-summary")
            self.assertIn("× Error", str(summary.render()))

    async def test_dashboard_invalid_config_warning(self):
        controller = TuiController(
            fake_service(config_valid=False, config_status="invalid"),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            summary = app.screen.query_one("#dashboard-summary")
            self.assertIn("! Warning", str(summary.render()))

    async def test_status_screen_wordlist_error(self):
        controller = TuiController(
            fake_service(wordlist_error=ExitCode.PUSH_ABORT),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.click("#btn-status")
            await pilot.pause()
            content = app.screen.query_one("#status-content")
            self.assertIn("Wordlist error", str(content.render()))

    async def test_status_screen_destructive_risk(self):
        status = StatusSnapshot(
            wordlist_count=2,
            diffs=sample_status().diffs,
            skipped_unreadable=(),
            skipped_corrupt=(),
            destructive_risk="Large removal batch",
        )
        service = FakeTuiService(sample_dashboard(), status, sample_preview())
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.click("#btn-status")
            await pilot.pause()
            content = app.screen.query_one("#status-content")
            self.assertIn("Large removal batch", str(content.render()))

    async def test_status_screen_no_diffs(self):
        status = StatusSnapshot(
            wordlist_count=1,
            diffs=(),
            skipped_unreadable=(),
            skipped_corrupt=(),
        )
        service = FakeTuiService(
            sample_dashboard(),
            status,
            sample_preview(),
        )
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.click("#btn-status")
            await pilot.pause()
            content = app.screen.query_one("#status-content")
            self.assertIn("No dictionary diffs", str(content.render()))

    async def test_preview_refresh_and_unchanged_row(self):
        controller = TuiController(fake_service(preview_unchanged=True), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.press("p")
            await pilot.pause()
            await pilot.press("r")
            await pilot.pause()
            summary = app.screen.query_one("#preview-content")
            self.assertIn("Total additions: 0", str(summary.render()))
            table = app.screen.query_one("#preview-table")
            self.assertEqual(table.row_count, 1)

    async def test_preview_plan_blocked(self):
        controller = TuiController(fake_service(plan_blocked=True), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.press("p")
            await pilot.pause()
            summary = app.screen.query_one("#preview-content")
            self.assertIn("Plan blocked", str(summary.render()))

    async def test_preview_wordlist_error(self):
        controller = TuiController(
            fake_service(wordlist_error=ExitCode.PUSH_ABORT),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.press("p")
            await pilot.pause()
            summary = app.screen.query_one("#preview-content")
            self.assertIn("Preview unavailable", str(summary.render()))

    async def test_status_screen_from_button(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.click("#btn-status")
            await pilot.pause()
            self.assertIsInstance(app.screen, StatusScreen)
            content = app.screen.query_one("#status-content")
            self.assertIn("chrome", str(content.render()))

    async def test_preview_screen_from_hotkey(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.press("p")
            await pilot.pause()
            self.assertIsInstance(app.screen, PreviewScreen)
            summary = app.screen.query_one("#preview-content")
            self.assertIn("Total removals: 2", str(summary.render()))

    async def test_escape_returns_to_dashboard(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.press("p")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_disabled_action_shows_notice(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, DashboardScreen)
            event = mock.MagicMock()
            event.button.id = "btn-push"
            screen.on_button_pressed(event)
            await pilot.pause()

    async def test_quit_button_handler_exits(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, DashboardScreen)
            event = mock.MagicMock()
            event.button.id = "btn-quit"
            screen.on_button_pressed(event)
            await pilot.pause()

    async def test_status_escape_returns_to_dashboard(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.click("#btn-status")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_narrow_terminal_warning(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(60, 20)) as pilot:
            await pilot.pause()
            warning = app.screen.query_one("#narrow-warning")
            self.assertIn("80x24", str(warning.render()))

    def test_css_is_packaged(self):
        css_path = resources.files("spell_sync.tui").joinpath("app.tcss")
        self.assertTrue(css_path.is_file())
        self.assertIn("dashboard-summary", css_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
