"""Headless Pull flow tests."""

import unittest

from spell_sync.application.product_concepts import (
    COLLECT_CONFIRM_BUTTON,
    COLLECT_WORDS_LABEL,
    CONTINUE_TO_UPDATE_APPS_LABEL,
    REVIEW_EXTRA_WORDS_LABEL,
)
from spell_sync.application.reports import OperationOutcome, OperationReport, PullExecution
from spell_sync.application.requests import ProjectRef
from spell_sync.cli_options import CliOptions
from spell_sync.exit_codes import ExitCode
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.dashboard import DashboardScreen
from spell_sync.tui.screens.preview_screen import PreviewScreen
from spell_sync.tui.screens.pull_screen import PullScreen
from spell_sync.tui.screens.report_screen import ReportScreen
from tests.tui.fake_service import fake_service, sample_extra_inventory, sample_pull_preview
from tests.tui.test_helpers import wait_for_operation_report, wait_for_text


class TestPullFlow(unittest.IsolatedAsyncioTestCase):
    async def test_preview_fields_and_refresh(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.click("#btn-pull")
            content = await wait_for_text(pilot, "#pull-summary", "custom diction")
            text = str(content.render())
            self.assertIn("17 words from your apps are not in your list yet", text)
            self.assertRegex(text, r"Dictionaries ready:\s+2")
            self.assertRegex(text, r"Dictionaries skipped:\s+1")
            self.assertNotIn("Apps ready", text)
            self.assertIn("! Skipped unreadable: offline", text)
            first_counter = service.pull_counter
            await pilot.click("#btn-refresh")
            await wait_for_text(pilot, "#pull-summary", "17 words from your apps")
            self.assertGreater(service.pull_counter, first_counter)

    async def test_confirmation_and_success_report(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PullScreen(controller))
            await wait_for_text(pilot, "#pull-summary", "custom diction")
            await pilot.click("#btn-run")
            await wait_for_text(pilot, "#confirm-summary", "Add 17 words")
            await pilot.click("#btn-run")
            await wait_for_operation_report(pilot, "Collect my words completed")
            self.assertEqual(service.execute_pull_calls, 1)
            continue_btn = app.screen.query_one("#btn-continue-update")
            self.assertEqual(str(continue_btn.label), CONTINUE_TO_UPDATE_APPS_LABEL)
            await pilot.click("#btn-continue-update")
            await wait_for_text(pilot, "#preview-content", "Update my apps")
            self.assertIsInstance(app.screen, PreviewScreen)

    async def test_confirm_covers_parent_preview_actions(self):
        """Parent View additions / Back must not show through under Cancel."""
        controller = TuiController(fake_service(), ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PullScreen(controller))
            await wait_for_text(pilot, "#pull-summary", "custom diction")
            preview_run = app.screen.query_one("#btn-run")
            self.assertEqual(str(preview_run.label), COLLECT_WORDS_LABEL)
            await pilot.click("#btn-run")
            await wait_for_text(pilot, "#confirm-summary", "Add 17 words")
            screen = app.screen
            self.assertEqual(str(screen.query_one("#btn-run").label), COLLECT_CONFIRM_BUTTON)
            self.assertEqual(len(screen.query("#btn-view-additions")), 0)
            self.assertEqual(len(screen.query("#btn-back")), 0)
            buttons = [
                child
                for child in screen.query_one("#screen-actions").children
                if child.id and str(child.id).startswith("btn-") and child.display
            ]
            self.assertEqual([button.id for button in buttons], ["btn-run", "btn-cancel"])
            body = screen.query_one("#confirm-body")
            self.assertGreaterEqual(body.region.height, 20)

    async def test_cancel_before_execution(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PullScreen(controller))
            await wait_for_text(pilot, "#pull-summary", "custom diction")
            await pilot.click("#btn-run")
            await wait_for_text(pilot, "#confirm-summary", "Add 17 words")
            await pilot.click("#btn-cancel")
            await pilot.pause()
            self.assertEqual(service.execute_pull_calls, 0)
            self.assertIsInstance(app.screen, PullScreen)

    async def test_service_failure(self):
        preview = sample_pull_preview()
        service = fake_service(
            pull_execution=PullExecution(
                preview=preview,
                result=ExitCode.PUSH_ABORT,
                outcome=OperationOutcome.FAILED,
                message="write failed",
            )
        )
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PullScreen(controller))
            await wait_for_text(pilot, "#pull-summary", "custom diction")
            await pilot.click("#btn-run")
            await wait_for_text(pilot, "#confirm-summary", "Add 17 words")
            await pilot.click("#btn-run")
            await wait_for_operation_report(pilot, "Collect my words failed")
            self.assertEqual(len(app.screen.query("#btn-continue-update")), 0)

    async def test_back_navigation(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.click("#btn-pull")
            await wait_for_text(pilot, "#pull-summary", "custom diction")
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_double_run_guard(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            screen = PullScreen(controller)
            app.push_screen(screen)
            await wait_for_text(pilot, "#pull-summary", "custom diction")
            screen._starting = True
            screen.action_run_pull()
            self.assertEqual(service.execute_pull_calls, 0)

    async def test_preview_offers_extra_words_when_additions_exist(self):
        service = fake_service(extra_inventory=sample_extra_inventory(count=2))
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PullScreen(controller))
            await wait_for_text(pilot, "#pull-summary", "custom diction")
            extra = app.screen.query_one("#btn-extra-words")
            self.assertTrue(extra.display)
            self.assertEqual(str(extra.label), REVIEW_EXTRA_WORDS_LABEL)
            await pilot.click("#btn-extra-words")
            await wait_for_text(pilot, "#extra-words-heading", "Extra words")

    async def test_empty_collect_offers_update(self):
        preview = sample_pull_preview(additions=0, addition_words=frozenset())
        controller = TuiController(fake_service(pull_preview=preview), ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PullScreen(controller))
            await wait_for_text(pilot, "#pull-summary", "No new words")
            self.assertIn(
                "Next: Update my apps.", str(app.screen.query_one("#pull-summary").render())
            )
            self.assertFalse(app.screen.query_one("#btn-extra-words").display)
            self.assertFalse(app.screen.query_one("#btn-run").display)
            next_btn = app.screen.query_one("#btn-next-step")
            self.assertTrue(next_btn.display)
            self.assertEqual(str(next_btn.label), CONTINUE_TO_UPDATE_APPS_LABEL)
            await pilot.click("#btn-next-step")
            await wait_for_text(pilot, "#preview-content", "Update my apps")
            self.assertIsInstance(app.screen, PreviewScreen)

    async def test_empty_list_collect_routes_to_add_words(self):
        preview = sample_pull_preview(
            additions=0,
            before_count=0,
            after_count=0,
            addition_words=frozenset(),
        )
        controller = TuiController(fake_service(pull_preview=preview), ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PullScreen(controller))
            await wait_for_text(pilot, "#pull-summary", "list is empty")
            next_btn = app.screen.query_one("#btn-next-step")
            self.assertTrue(next_btn.display)
            self.assertEqual(str(next_btn.label), "Add words to my list")
            await pilot.click("#btn-next-step")
            from spell_sync.tui.screens.first_win_screen import AddWordsScreen

            self.assertIsInstance(app.screen, AddWordsScreen)

    async def test_collect_report_hides_update_when_list_empty(self):
        controller = TuiController(fake_service(empty_wordlist=True), ProjectRef())
        app = SpellSyncApp(controller)
        report = OperationReport(
            operation="pull",
            outcome=OperationOutcome.COMPLETED,
            title="Collect my words completed",
            summary="No new personal words were found.",
        )
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(ReportScreen(controller, report))
            await wait_for_text(pilot, "#report-content", "Collect my words completed")
            self.assertEqual(len(app.screen.query("#btn-continue-update")), 0)


if __name__ == "__main__":
    unittest.main()
