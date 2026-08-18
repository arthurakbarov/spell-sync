"""Extra-words TUI: paging, global toggle, keep then wipe."""

import tempfile
import unittest
from pathlib import Path

from spell_sync.application.extra_words import ExtraWordsWipeResult
from spell_sync.application.product_concepts import (
    CONTINUE_TO_UPDATE_APPS_LABEL,
    EXTRA_WORDS_ADD_LABEL,
    EXTRA_WORDS_CONTINUE_TO_REMOVE_LABEL,
    EXTRA_WORDS_DONE_HINT,
    EXTRA_WORDS_HEADING,
    EXTRA_WORDS_REMOVE_LABEL,
    EXTRA_WORDS_SKIP_TO_REMOVE_LABEL,
    EXTRA_WORDS_WIPE_HEADING,
    REVIEW_EXTRA_WORDS_LABEL,
)
from spell_sync.cli_options import CliOptions
from spell_sync.io import write_text_words
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.extra_words_screen import EXTRA_WORDS_PAGE_SIZE, ExtraWordsScreen
from spell_sync.tui.screens.preview_screen import PreviewScreen
from spell_sync.tui.screens.pull_screen import PullScreen
from tests.tui.fake_service import fake_service, sample_extra_inventory
from tests.tui.test_helpers import wait_for_text


def _row_text(table, index: int) -> str:
    return " ".join(str(cell) for cell in table.get_row_at(index))


def _displayed_action_buttons(screen):
    return [
        child
        for child in screen.query_one("#screen-actions").children
        if child.id and child.id.startswith("btn-") and child.display
    ]


def _assert_stacked_action_indent(test, buttons) -> None:
    test.assertGreaterEqual(len(buttons), 2)
    test.assertEqual({button.region.width for button in buttons}, {36})
    test.assertEqual({button.region.x for button in buttons}, {buttons[0].region.x})
    gaps = [
        buttons[index + 1].region.y - (buttons[index].region.y + buttons[index].region.height)
        for index in range(len(buttons) - 1)
    ]
    test.assertTrue(all(gap == gaps[0] for gap in gaps), gaps)
    test.assertGreaterEqual(gaps[0], 0)


class TestExtraWordsScreen(unittest.IsolatedAsyncioTestCase):
    async def test_dashboard_opens_extra_words(self) -> None:
        controller = TuiController(
            fake_service(extra_inventory=sample_extra_inventory(count=3)),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.click("#btn-extra-words")
            await wait_for_text(pilot, "#extra-words-heading", EXTRA_WORDS_HEADING)
            self.assertIsInstance(app.screen, ExtraWordsScreen)
            table = app.screen.query_one("#extra-words-table")
            self.assertEqual(table.row_count, 3)
            self.assertIn("chrome, firefox", _row_text(table, 0))

    async def test_toggle_all_includes_off_page_rows(self) -> None:
        count = EXTRA_WORDS_PAGE_SIZE + 2
        controller = TuiController(
            fake_service(extra_inventory=sample_extra_inventory(count=count)),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(ExtraWordsScreen(controller))
            await wait_for_text(pilot, "#extra-words-heading", EXTRA_WORDS_HEADING)
            screen = app.screen
            assert isinstance(screen, ExtraWordsScreen)
            table = screen.query_one("#extra-words-table")
            self.assertEqual(table.row_count, EXTRA_WORDS_PAGE_SIZE)
            self.assertTrue(_row_text(table, 0).startswith("·"))
            await pilot.click("#btn-toggle-all")
            await pilot.pause()
            table = screen.query_one("#extra-words-table")
            self.assertTrue(_row_text(table, 0).startswith("✓"))
            await pilot.click("#btn-next")
            await wait_for_text(pilot, "#extra-words-page", "Page 2 of 2")
            table = screen.query_one("#extra-words-table")
            self.assertEqual(table.row_count, 2)
            self.assertTrue(_row_text(table, 0).startswith("✓"))
            self.assertTrue(_row_text(table, 1).startswith("✓"))
            self.assertEqual(len(screen._selected), count)

    async def test_keep_subset_then_wipe_remaining(self) -> None:
        count = EXTRA_WORDS_PAGE_SIZE + 2
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            write_text_words(str(wordlist), ["seed"], "utf-8", False, quiet=True)
            service = fake_service(extra_inventory=sample_extra_inventory(count=count))
            controller = TuiController(service, CliOptions())
            controller.set_project_wordlist(wordlist)
            app = SpellSyncApp(controller)
            async with app.run_test(size=(100, 48)) as pilot:
                app.push_screen(ExtraWordsScreen(controller))
                await wait_for_text(pilot, "#extra-words-heading", EXTRA_WORDS_HEADING)
                screen = app.screen
                assert isinstance(screen, ExtraWordsScreen)
                await pilot.click("#btn-toggle-all")
                await pilot.click("#btn-next")
                await wait_for_text(pilot, "#extra-words-page", "Page 2 of 2")
                table = screen.query_one("#extra-words-table")
                table.focus()
                await pilot.press("enter")
                await pilot.pause()
                self.assertNotIn("extra08", screen._selected)
                await pilot.click("#btn-add")
                await wait_for_text(pilot, "#extra-words-heading", EXTRA_WORDS_WIPE_HEADING)
                table = screen.query_one("#extra-words-table")
                self.assertEqual(table.row_count, 1)
                self.assertIn("extra08", _row_text(table, 0))
                self.assertTrue(_row_text(table, 0).startswith("✓"))
                self.assertIn("extra00", wordlist.read_text(encoding="utf-8"))
                self.assertNotIn("extra08", wordlist.read_text(encoding="utf-8"))
                await pilot.click("#btn-remove")
                await wait_for_text(pilot, "#extra-words-hint", EXTRA_WORDS_DONE_HINT)
                continue_btn = app.screen.query_one("#btn-continue-update")
                self.assertTrue(continue_btn.display)
                self.assertEqual(str(continue_btn.label), CONTINUE_TO_UPDATE_APPS_LABEL)
                self.assertEqual(service.subtract_extra_words_calls, 1)
                self.assertEqual(service.last_subtracted_words, ("extra08",))
                await pilot.click("#btn-continue-update")
                await wait_for_text(pilot, "#preview-content", "Update my apps")
                self.assertIsInstance(app.screen, PreviewScreen)

    async def test_empty_keep_advances_and_empty_wipe_finishes(self) -> None:
        service = fake_service(extra_inventory=sample_extra_inventory(count=2))
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(ExtraWordsScreen(controller))
            await wait_for_text(pilot, "#extra-words-heading", EXTRA_WORDS_HEADING)
            add_btn = app.screen.query_one("#btn-add")
            skip_btn = app.screen.query_one("#btn-skip-remove")
            self.assertFalse(add_btn.display)
            self.assertEqual(str(skip_btn.label), EXTRA_WORDS_CONTINUE_TO_REMOVE_LABEL)
            await pilot.click("#btn-skip-remove")
            await wait_for_text(pilot, "#extra-words-heading", EXTRA_WORDS_WIPE_HEADING)
            table = app.screen.query_one("#extra-words-table")
            self.assertEqual(table.row_count, 2)
            self.assertTrue(_row_text(table, 0).startswith("✓"))
            await pilot.click("#btn-toggle-all")
            await pilot.pause()
            self.assertTrue(_row_text(table, 0).startswith("·"))
            remove_btn = app.screen.query_one("#btn-remove")
            self.assertEqual(str(remove_btn.label), EXTRA_WORDS_REMOVE_LABEL)
            await pilot.click("#btn-remove")
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            self.assertEqual(service.last_subtracted_words, ())

    async def test_checked_keep_shows_add_and_skip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            write_text_words(str(wordlist), ["seed"], "utf-8", False, quiet=True)
            service = fake_service(extra_inventory=sample_extra_inventory(count=2))
            controller = TuiController(service, CliOptions())
            controller.set_project_wordlist(wordlist)
            app = SpellSyncApp(controller)
            async with app.run_test(size=(100, 48)) as pilot:
                app.push_screen(ExtraWordsScreen(controller))
                await wait_for_text(pilot, "#extra-words-heading", EXTRA_WORDS_HEADING)
                await pilot.click("#btn-toggle-all")
                await pilot.pause()
                add_btn = app.screen.query_one("#btn-add")
                skip_btn = app.screen.query_one("#btn-skip-remove")
                self.assertTrue(add_btn.display)
                self.assertEqual(str(add_btn.label), EXTRA_WORDS_ADD_LABEL)
                self.assertEqual(add_btn.variant, "primary")
                self.assertEqual(str(skip_btn.label), EXTRA_WORDS_SKIP_TO_REMOVE_LABEL)
                self.assertEqual(skip_btn.variant, "default")
                await pilot.click("#btn-skip-remove")
                await wait_for_text(pilot, "#extra-words-heading", EXTRA_WORDS_WIPE_HEADING)
                self.assertNotIn("extra00", wordlist.read_text(encoding="utf-8"))
                table = app.screen.query_one("#extra-words-table")
                self.assertEqual(table.row_count, 2)

    async def test_dashboard_button_label(self) -> None:
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            button = app.screen.query_one("#btn-extra-words")
            self.assertEqual(str(button.label), REVIEW_EXTRA_WORDS_LABEL)
            self.assertFalse(button.disabled)

    async def test_keep_action_buttons_share_indent_and_gaps(self) -> None:
        controller = TuiController(
            fake_service(extra_inventory=sample_extra_inventory(count=3)),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(ExtraWordsScreen(controller))
            await wait_for_text(pilot, "#extra-words-heading", EXTRA_WORDS_HEADING)
            screen = app.screen
            buttons = _displayed_action_buttons(screen)
            self.assertEqual(
                [button.id for button in buttons],
                ["btn-skip-remove", "btn-toggle-all", "btn-find", "btn-back"],
            )
            _assert_stacked_action_indent(self, buttons)
            self.assertFalse(screen.query_one("#btn-add").display)
            self.assertFalse(screen.query_one("#btn-remove").display)
            self.assertFalse(screen.query_one("#btn-continue-update").display)
            self.assertFalse(screen.query_one("#btn-prev").display)
            self.assertFalse(screen.query_one("#btn-next").display)
            table = screen.query_one("#extra-words-table")
            gap = buttons[0].region.y - (table.region.y + table.region.height)
            self.assertGreaterEqual(gap, 1)
            self.assertLessEqual(gap, 3)
            body = screen.query_one("#screen-body")
            actions = screen.query_one("#screen-actions")
            self.assertIs(actions.parent, body)
            footer = screen.query_one("Footer")
            body.scroll_end(animate=False)
            await pilot.pause()
            back = screen.query_one("#btn-back")
            self.assertGreaterEqual(
                footer.region.y - (back.region.y + back.region.height),
                1,
            )

    async def test_wipe_action_buttons_share_indent_and_gaps(self) -> None:
        controller = TuiController(
            fake_service(extra_inventory=sample_extra_inventory(count=2)),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(ExtraWordsScreen(controller))
            await wait_for_text(pilot, "#extra-words-heading", EXTRA_WORDS_HEADING)
            await pilot.click("#btn-skip-remove")
            await wait_for_text(pilot, "#extra-words-heading", EXTRA_WORDS_WIPE_HEADING)
            screen = app.screen
            buttons = _displayed_action_buttons(screen)
            self.assertEqual(
                [button.id for button in buttons],
                ["btn-remove", "btn-toggle-all", "btn-back"],
            )
            _assert_stacked_action_indent(self, buttons)
            self.assertFalse(screen.query_one("#btn-add").display)
            self.assertFalse(screen.query_one("#btn-skip-remove").display)
            self.assertFalse(screen.query_one("#btn-find").display)

    async def test_action_indent_matches_collect_preview(self) -> None:
        extra_controller = TuiController(
            fake_service(extra_inventory=sample_extra_inventory(count=2)),
            CliOptions(),
        )
        extra_app = SpellSyncApp(extra_controller)
        extra_x = extra_width = None
        async with extra_app.run_test(size=(100, 48)) as pilot:
            extra_app.push_screen(ExtraWordsScreen(extra_controller))
            await wait_for_text(pilot, "#extra-words-heading", EXTRA_WORDS_HEADING)
            extra = extra_app.screen.query_one("#btn-skip-remove")
            extra_x = extra.region.x
            extra_width = extra.region.width
        pull_controller = TuiController(fake_service(), CliOptions())
        pull_app = SpellSyncApp(pull_controller)
        async with pull_app.run_test(size=(100, 48)) as pilot:
            pull_app.push_screen(PullScreen(pull_controller))
            await wait_for_text(pilot, "#pull-summary", "Collect")
            run = pull_app.screen.query_one("#btn-run")
            self.assertEqual(run.region.width, extra_width)
            self.assertEqual(run.region.width, 36)
            self.assertEqual(run.region.x, extra_x)

    async def test_actions_inside_body_on_compact_terminal(self) -> None:
        controller = TuiController(
            fake_service(extra_inventory=sample_extra_inventory(count=3)),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(80, 24)) as pilot:
            app.push_screen(ExtraWordsScreen(controller))
            await wait_for_text(pilot, "#extra-words-heading", EXTRA_WORDS_HEADING)
            body = app.screen.query_one("#screen-body")
            actions = app.screen.query_one("#screen-actions")
            self.assertIs(actions.parent, body)
            self.assertGreaterEqual(body.region.height, 12)
            skip_btn = app.screen.query_one("#btn-skip-remove")
            self.assertEqual(skip_btn.region.width, 36)
            self.assertGreater(skip_btn.region.height, 0)

    async def test_wipe_writes_offer_update_when_list_has_words(self) -> None:
        service = fake_service(
            extra_inventory=sample_extra_inventory(count=2),
            extra_wipe_result=ExtraWordsWipeResult(ok=True, written=("chrome",), skipped=()),
        )
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(ExtraWordsScreen(controller))
            await wait_for_text(pilot, "#extra-words-heading", EXTRA_WORDS_HEADING)
            await pilot.click("#btn-skip-remove")
            await wait_for_text(pilot, "#extra-words-heading", EXTRA_WORDS_WIPE_HEADING)
            await pilot.click("#btn-remove")
            await wait_for_text(pilot, "#extra-words-hint", EXTRA_WORDS_DONE_HINT)
            self.assertTrue(app.screen.query_one("#btn-continue-update").display)
            self.assertIsInstance(app.screen, ExtraWordsScreen)

    async def test_adding_all_extras_offers_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            write_text_words(str(wordlist), ["seed"], "utf-8", False, quiet=True)
            service = fake_service(extra_inventory=sample_extra_inventory(count=2))
            controller = TuiController(service, CliOptions())
            controller.set_project_wordlist(wordlist)
            app = SpellSyncApp(controller)
            async with app.run_test(size=(100, 48)) as pilot:
                app.push_screen(ExtraWordsScreen(controller))
                await wait_for_text(pilot, "#extra-words-heading", EXTRA_WORDS_HEADING)
                await pilot.click("#btn-toggle-all")
                await pilot.click("#btn-add")
                await wait_for_text(pilot, "#extra-words-hint", EXTRA_WORDS_DONE_HINT)
                self.assertTrue(app.screen.query_one("#btn-continue-update").display)
                self.assertFalse(app.screen.query_one("#extra-words-table").display)


if __name__ == "__main__":
    unittest.main()
