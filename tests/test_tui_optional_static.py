"""Optional status/placeholder Statics hide when blank."""

import unittest

from textual.app import App, ComposeResult
from textual.widgets import Static

from spell_sync.tui.layout import action_bar, set_optional_static


class _Harness(App[None]):
    def compose(self) -> ComposeResult:
        yield Static(id="probe")
        yield action_bar(status_id="bar-status")


class TestOptionalStatic(unittest.IsolatedAsyncioTestCase):
    async def test_set_optional_static_hides_blank(self) -> None:
        app = _Harness()
        async with app.run_test():
            probe = app.query_one("#probe", Static)
            set_optional_static(probe, "")
            self.assertFalse(probe.display)
            set_optional_static(probe, "  hello  ")
            self.assertTrue(probe.display)
            self.assertEqual(str(probe.render()).strip(), "hello")
            set_optional_static(probe, "   ")
            self.assertFalse(probe.display)

    async def test_action_bar_blank_status_starts_hidden(self) -> None:
        app = _Harness()
        async with app.run_test():
            status = app.query_one("#bar-status", Static)
            self.assertFalse(status.display)
            set_optional_static(status, "Saved")
            self.assertTrue(status.display)

    async def test_doctor_export_status_starts_hidden(self) -> None:
        from spell_sync.cli_options import CliOptions
        from spell_sync.tui.app import SpellSyncApp
        from spell_sync.tui.controller import TuiController
        from spell_sync.tui.screens.doctor_screen import DoctorScreen
        from tests.tui.fake_service import fake_service

        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(DoctorScreen(controller))
            await pilot.pause()
            status = app.screen.query_one("#doctor-export-status", Static)
            self.assertFalse(status.display)
