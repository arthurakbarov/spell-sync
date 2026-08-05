"""Worker behaviour tests."""

from __future__ import annotations

import unittest

from spell_sync.application.reports import StatusDetailSnapshot
from spell_sync.application.requests import ProjectRef
from spell_sync.cli_options import CliOptions
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.dashboard import DashboardScreen
from spell_sync.tui.screens.status_screen import StatusScreen
from spell_sync.tui.workers import LoadTokenMixin
from tests.tui.fake_service import (
    FakeTuiService,
    fake_service,
    sample_dashboard,
    sample_doctor,
    sample_preview,
    sample_status,
    sample_status_detail,
)
from tests.tui.test_helpers import wait_for_text


class _MountedScreen(LoadTokenMixin):
    is_mounted = True  # type: ignore[misc]


class TestWorkers(unittest.IsolatedAsyncioTestCase):
    def test_stale_load_token_is_ignored(self):
        screen = _MountedScreen()
        first = screen._begin_load()
        second = screen._begin_load()
        self.assertFalse(screen._is_current_load(first))
        self.assertTrue(screen._is_current_load(second))

    async def test_dashboard_refresh_completes(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            app.screen.refresh_dashboard()
            await wait_for_text(pilot, "#dashboard-summary", "Ready")

    async def test_loading_state(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            app.screen.refresh_dashboard()
            summary = app.screen.query_one("#dashboard-summary")
            self.assertIn("Loading dashboard", str(summary.render()))
            await wait_for_text(pilot, "#dashboard-summary", "Ready")

    async def test_close_screen_during_worker(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            app.push_screen(StatusScreen(controller))
            await pilot.pause()
            app.pop_screen()
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_exception_becomes_controlled_error(self):
        class ExplodingService(FakeTuiService):
            def load_status_detail(self, opts: CliOptions) -> StatusDetailSnapshot:
                raise RuntimeError("boom")

        from tests.tui.fake_service import sample_pull_preview

        service = ExplodingService(
            sample_dashboard(),
            sample_status(),
            sample_status_detail(),
            sample_preview(),
            sample_doctor(),
            sample_pull_preview(),
        )
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.switch_screen(StatusScreen(controller))
            content = await wait_for_text(pilot, "#status-summary", "load failed")
            text = str(content.render())
            self.assertIn("load failed", text)
            self.assertNotIn("Traceback", text)


if __name__ == "__main__":
    unittest.main()
