"""First-win and add-words TUI screens."""

import tempfile
import unittest
from pathlib import Path

from spell_sync.application.product_concepts import (
    CONTINUE_TO_UPDATE_APPS_LABEL,
    FIRST_WIN_COLLECT_LABEL,
)
from spell_sync.application.reports import OperationOutcome, OperationReport
from spell_sync.cli_options import CliOptions
from spell_sync.io import write_text_words
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.dashboard import DashboardScreen
from spell_sync.tui.screens.first_win_screen import AddWordsScreen, FirstWinScreen
from spell_sync.tui.screens.report_screen import ReportScreen
from spell_sync.tui.screens.review_update_screen import ReviewStartScreen
from tests.tui.fake_service import fake_service
from tests.tui.test_helpers import wait_for_text


class TestFirstWinFlow(unittest.IsolatedAsyncioTestCase):
    async def test_setup_report_opens_first_win(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        report = OperationReport(
            operation="setup",
            outcome=OperationOutcome.COMPLETED_WITH_WARNINGS,
            title="Project created with warnings",
            summary="Created with warnings",
            details=("note",),
        )
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(ReportScreen(controller, report))
            await wait_for_text(pilot, "#report-content", "Project created")
            self.assertEqual(len(app.screen.query("#btn-continue-update")), 0)
            await pilot.click("#btn-dashboard")
            await wait_for_text(pilot, "#first-win-intro", "Setup is done")
            self.assertIsInstance(app.screen, FirstWinScreen)
            await pilot.click("#btn-dashboard")
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_collect_choice_opens_review_not_standalone_collect(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(FirstWinScreen(controller))
            await wait_for_text(pilot, "#first-win-intro", "Setup is done")
            collect = app.screen.query_one("#btn-collect")
            self.assertEqual(str(collect.label), FIRST_WIN_COLLECT_LABEL)
            await pilot.click("#btn-collect")
            await wait_for_text(pilot, "#review-body", "Nothing changes until you confirm")
            self.assertIsInstance(app.screen, ReviewStartScreen)

    async def test_add_words_saves_and_enables_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            write_text_words(str(wordlist), ["seed"], "utf-8", False, quiet=True)
            controller = TuiController(fake_service(), CliOptions())
            controller.set_project_wordlist(wordlist)
            app = SpellSyncApp(controller)
            async with app.run_test(size=(100, 48)) as pilot:
                await wait_for_text(pilot, "#dashboard-summary", "Ready")
                app.push_screen(AddWordsScreen(controller))
                await wait_for_text(pilot, "#add-words-intro", "One word")
                area = app.screen.query_one("#add-words-input")
                area.text = "AcmeCorp\n"
                await pilot.click("#btn-save")
                await wait_for_text(pilot, "#add-words-status", "Saved to your word list")
                update_btn = app.screen.query_one("#btn-update")
                self.assertFalse(update_btn.disabled)
                self.assertEqual(str(update_btn.label), CONTINUE_TO_UPDATE_APPS_LABEL)
                self.assertIn("AcmeCorp", wordlist.read_text(encoding="utf-8"))

    async def test_add_words_unreadable_uses_guest_copy(self):
        from spell_sync.application.product_concepts import WORD_LIST_UNREADABLE_STATUS

        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\x00\n", encoding="utf-8")
            controller = TuiController(fake_service(), CliOptions())
            controller.set_project_wordlist(wordlist)
            app = SpellSyncApp(controller)
            notes: list[str] = []
            async with app.run_test(size=(100, 48)) as pilot:
                app.push_screen(AddWordsScreen(controller))
                await wait_for_text(pilot, "#add-words-intro", "One word")
                screen = app.screen
                screen.notify = lambda msg, **_kw: notes.append(msg)
                area = screen.query_one("#add-words-input")
                area.text = "AcmeCorp\n"
                await pilot.click("#btn-save")
                await pilot.pause()
            self.assertEqual(notes, [WORD_LIST_UNREADABLE_STATUS])
            self.assertTrue(all(str(wordlist) not in note for note in notes))
            self.assertEqual(wordlist.read_text(encoding="utf-8"), "alpha\x00\n")
