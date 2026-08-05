"""Status screen headless tests."""

from __future__ import annotations

import unittest

from textual.widgets import DataTable

from spell_sync.application.reports import TargetStatusRow
from spell_sync.cli_options import CliOptions
from spell_sync.exit_codes import ExitCode
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.dashboard import DashboardScreen
from spell_sync.tui.screens.status_screen import StatusScreen
from tests.tui.fake_service import fake_service, sample_status_detail
from tests.tui.test_helpers import wait_for_text


class TestStatusScreen(unittest.IsolatedAsyncioTestCase):
    async def test_target_rows(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.press("s")
            await wait_for_text(pilot, "#status-summary", "Wordlist")
            table = app.screen.query_one("#status-table", DataTable)
            self.assertGreaterEqual(table.row_count, 1)
            row_text = " ".join(str(cell) for cell in table.get_row_at(0))
            self.assertIn("chrome", row_text.lower())
            self.assertIn("yes", row_text.lower())

    async def test_disabled_unavailable_corrupt_targets(self):
        detail = sample_status_detail(
            targets=(
                TargetStatusRow(
                    name="broken",
                    enabled=True,
                    available=False,
                    read_status="corrupt",
                    path="/tmp/broken.txt",
                    format="text",
                    word_count=None,
                    detail="corrupt file",
                    skipped_reason="corrupt",
                ),
            ),
            skipped_corrupt=("broken",),
        )
        controller = TuiController(fake_service(status_detail=detail), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(StatusScreen(controller))
            content = await wait_for_text(pilot, "#status-summary", "Skipped corrupt")
            self.assertIn("Skipped corrupt", str(content.render()))
            table = app.screen.query_one("#status-table", DataTable)
            row_text = " ".join(str(cell) for cell in table.get_row_at(0))
            self.assertIn("corrupt", row_text)

    async def test_refresh_and_back(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(StatusScreen(controller))
            await wait_for_text(pilot, "#status-summary", "Wordlist")
            await pilot.press("r")
            await wait_for_text(pilot, "#status-summary", "Wordlist")
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_service_error(self):
        detail = sample_status_detail(load_error="Status could not be loaded.")
        controller = TuiController(fake_service(status_detail=detail), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(StatusScreen(controller))
            content = await wait_for_text(pilot, "#status-summary", "could not be loaded")
            self.assertIn("could not be loaded", str(content.render()))

    async def test_wordlist_error(self):
        detail = sample_status_detail(wordlist_error=ExitCode.PUSH_ABORT, wordlist_count=0)
        controller = TuiController(fake_service(status_detail=detail), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(StatusScreen(controller))
            content = await wait_for_text(pilot, "#status-summary", "Wordlist error")
            self.assertIn("Wordlist error", str(content.render()))


if __name__ == "__main__":
    unittest.main()
