"""Preview screen headless tests."""

from __future__ import annotations

import unittest

from spell_sync.application.reports import TargetPreview
from spell_sync.cli_options import CliOptions
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.preview_screen import PreviewScreen
from spell_sync.tui.screens.removals_screen import RemovalsScreen
from tests.tui.fake_service import fake_service, sample_preview
from tests.tui.test_helpers import wait_for_text


class TestPreviewScreen(unittest.IsolatedAsyncioTestCase):
    async def test_totals_and_table(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.click("#btn-push")
            summary = await wait_for_text(pilot, "#preview-content", "Total removals")
            self.assertIn("Total additions: 2", str(summary.render()))
            table = app.screen.query_one("#preview-table")
            self.assertEqual(table.row_count, 1)

    async def test_skipped_and_corrupt(self):
        preview = sample_preview(
            skipped=("offline",),
            corrupt=("broken",),
            warnings=("Skipped unreadable: offline",),
        )
        controller = TuiController(fake_service(preview=preview), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(PreviewScreen(controller))
            summary = await wait_for_text(pilot, "#preview-content", "Skipped")
            text = str(summary.render())
            self.assertIn("offline", text)
            self.assertIn("broken", text)

    async def test_view_removals(self):
        words = frozenset({f"word{i}" for i in range(50)})
        preview = sample_preview(
            targets=(
                TargetPreview(
                    name="chrome",
                    additions=0,
                    removals=len(words),
                    status="Review",
                    removal_words=words,
                ),
            ),
            removals=len(words),
        )
        controller = TuiController(fake_service(preview=preview), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Total removals")
            await pilot.click("#btn-view-removals")
            await pilot.pause()
            self.assertIsInstance(app.screen, RemovalsScreen)
            content = app.screen.query_one("#removals-content")
            self.assertIn("word0", str(content.render()))

    async def test_refresh_creates_new_preview(self):
        service = fake_service()
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Total additions")
            first_counter = service.preview_counter
            await pilot.click("#btn-refresh-preview")
            await wait_for_text(pilot, "#preview-content", "Total additions")
            self.assertGreater(service.preview_counter, first_counter)

    async def test_unchanged_target(self):
        preview = sample_preview(
            targets=(
                TargetPreview(
                    name="hunspell",
                    additions=0,
                    removals=0,
                    status="Unchanged",
                ),
            ),
            additions=0,
            removals=0,
            unchanged=1,
        )
        controller = TuiController(fake_service(preview=preview), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(PreviewScreen(controller))
            summary = await wait_for_text(pilot, "#preview-content", "Unchanged: 1")
            self.assertIn("Unchanged: 1", str(summary.render()))


if __name__ == "__main__":
    unittest.main()
