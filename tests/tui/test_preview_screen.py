"""Preview screen headless tests."""

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
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.click("#btn-push")
            summary = await wait_for_text(pilot, "#preview-content", "Removals")
            text = str(summary.render())
            self.assertRegex(text, r"Words to add\s*:\s*2")
            self.assertIn("Words to remove:", text)
            self.assertNotIn(" · ", text)
            table = app.screen.query_one("#preview-table")
            self.assertEqual(table.row_count, 1)

    async def test_actions_live_inside_body_scroll(self):
        """Regression: docked action bar stole height on 80 by 24."""
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(80, 24)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Words to add")
            body = app.screen.query_one("#screen-body")
            actions = app.screen.query_one("#screen-actions")
            self.assertIs(actions.parent, body)
            self.assertGreaterEqual(body.region.height, 12)
            back = app.screen.query_one("#btn-back")
            self.assertGreater(back.region.y, app.screen.query_one("#preview-content").region.y)

    async def test_body_full_bleed_content_centered_in_wide_terminal(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(160, 40)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Words to add")
            body = app.screen.query_one("#screen-body")
            content = app.screen.query_one("#preview-content")
            actions = app.screen.query_one("#screen-actions")
            # Scroll surface spans the terminal (scrollbar on the right wall).
            self.assertEqual(body.region.x, 0)
            self.assertEqual(body.region.width, 160)
            # Content column stays capped and roughly centered.
            self.assertLessEqual(content.region.width, 100)
            self.assertLessEqual(actions.region.width, 100)
            self.assertGreater(content.region.x, 0)
            right = 160 - (content.region.x + content.region.width)
            self.assertLessEqual(abs(content.region.x - right), 2)

    async def test_skipped_and_corrupt(self):
        preview = sample_preview(
            skipped=("offline",),
            corrupt=("broken",),
            warnings=("Skipped unreadable: offline",),
        )
        controller = TuiController(fake_service(preview=preview), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
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
                    name="sublime",
                    additions=0,
                    removals=0,
                    status="Unchanged",
                    removal_words=frozenset(),
                ),
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
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Removals")
            # Cursor stays on first row (sublime, 0 removals) — must still aggregate.
            await pilot.click("#btn-view-removals")
            await pilot.pause()
            self.assertIsInstance(app.screen, RemovalsScreen)
            removals = app.screen
            assert isinstance(removals, RemovalsScreen)
            self.assertEqual(removals._removal_words, words)
            self.assertIn("chrome", removals._title)
            content = app.screen.query_one("#removals-content")
            self.assertIn("word0", str(content.render()))
            self.assertNotIn("No words", str(content.render()))

    async def test_overlap_removals_counts_stay_aligned(self):
        preview = sample_preview(
            targets=(
                TargetPreview(
                    name="sublime",
                    additions=0,
                    removals=3,
                    status="Review",
                    removal_words=frozenset({"Huawei", "Jupyter", "Netflix"}),
                ),
                TargetPreview(
                    name="macos",
                    additions=0,
                    removals=4,
                    status="Review",
                    removal_words=frozenset({"Huawei", "Jupyter", "Netflix", "Sokoban"}),
                ),
            ),
            removals=7,
            additions=0,
            targets_to_update=2,
        )
        controller = TuiController(fake_service(preview=preview), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PreviewScreen(controller))
            summary = await wait_for_text(pilot, "#preview-content", "Words to remove:")
            rendered = str(summary.render())
            self.assertRegex(rendered, r"Words to remove:\s+4")
            self.assertNotIn("across apps", rendered)
            await pilot.click("#btn-view-removals")
            await pilot.pause()
            self.assertIsInstance(app.screen, RemovalsScreen)
            detail = await wait_for_text(pilot, "#removals-summary", "4 word(s)")
            self.assertIn("4 word(s)", str(detail.render()))
            self.assertNotIn("across apps", str(detail.render()))
            content = str(app.screen.query_one("#removals-content").render())
            self.assertIn("Huawei\n  sublime, macos", content)

    async def test_view_additions_skips_full_sync_dumps(self):
        from spell_sync.config import PUSH_SMALL_DELTA_REVIEW_MAX

        small = frozenset({"delta"})
        huge = frozenset({f"w{i}" for i in range(PUSH_SMALL_DELTA_REVIEW_MAX + 5)})
        preview = sample_preview(
            targets=(
                TargetPreview(
                    name="sublime",
                    additions=1,
                    removals=0,
                    status="Ready",
                    addition_words=small,
                ),
                TargetPreview(
                    name="chrome",
                    additions=len(huge),
                    removals=0,
                    status="Ready",
                    addition_words=huge,
                ),
            ),
            additions=1 + len(huge),
            removals=0,
            targets_to_update=2,
        )
        controller = TuiController(fake_service(preview=preview), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Words to add")
            await pilot.click("#btn-view-additions")
            await pilot.pause()
            self.assertIsInstance(app.screen, RemovalsScreen)
            summary = await wait_for_text(pilot, "#removals-summary", "Small-delta")
            self.assertIn("Omitted full sync: chrome", str(summary.render()))
            content = str(app.screen.query_one("#removals-content").render())
            self.assertIn("delta", content)
            self.assertNotIn("w0", content)

    async def test_refresh_creates_new_preview(self):
        service = fake_service()
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Words to add")
            first_counter = service.preview_counter
            await pilot.click("#btn-refresh-preview")
            await wait_for_text(pilot, "#preview-content", "Words to add")
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
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PreviewScreen(controller))
            summary = await wait_for_text(pilot, "#preview-content", "Unchanged")
            self.assertRegex(str(summary.render()), r"Unchanged\s*:\s*1")


if __name__ == "__main__":
    unittest.main()
