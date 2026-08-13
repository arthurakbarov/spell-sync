"""Headless Pull flow tests."""

import unittest

from spell_sync.application.reports import OperationOutcome, PullExecution
from spell_sync.application.requests import ProjectRef
from spell_sync.cli_options import CliOptions
from spell_sync.exit_codes import ExitCode
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.dashboard import DashboardScreen
from spell_sync.tui.screens.pull_screen import PullScreen
from tests.tui.fake_service import fake_service, sample_pull_preview
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
            self.assertIn("Apps ready: 2", text)
            self.assertIn("skipped: 1", text)
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


if __name__ == "__main__":
    unittest.main()
