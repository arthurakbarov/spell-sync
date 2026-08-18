"""Basic Textual app navigation tests."""

import unittest
from importlib import resources
from unittest import mock

from spell_sync.cli_options import CliOptions
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.dashboard import DashboardScreen
from spell_sync.tui.screens.preview_screen import PreviewScreen
from spell_sync.tui.screens.status_screen import StatusScreen
from tests.tui.fake_service import fake_service
from tests.tui.test_helpers import wait_for_text


class TestSpellSyncApp(unittest.IsolatedAsyncioTestCase):
    async def test_dashboard_mounts(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Your personal word list")
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_quit_button_exits(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            event = mock.MagicMock()
            event.button.id = "btn-quit"
            app.screen.on_button_pressed(event)
            await pilot.pause()

    async def test_status_navigation(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.press("s")
            await pilot.pause()
            self.assertIsInstance(app.screen, StatusScreen)

    async def test_status_navigation_under_russian_layout(self):
        # "ы" sits at the same physical key as "s" on a Russian keyboard.
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.press("ы")
            await pilot.pause()
            self.assertIsInstance(app.screen, StatusScreen)

    async def test_preview_navigation(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.click("#btn-push")
            await pilot.pause()
            await wait_for_text(pilot, "#preview-content", "Removals")
            self.assertIsInstance(app.screen, PreviewScreen)

    async def test_escape_returns_to_dashboard(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.click("#btn-push")
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
            self.assertIn("80 by 24", str(warning.render()))

    def test_css_is_packaged(self):
        css_path = resources.files("spell_sync.tui").joinpath("app.tcss")
        self.assertTrue(css_path.is_file())
        self.assertIn("dashboard-summary", css_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
