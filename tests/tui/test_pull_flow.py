"""Headless Pull flow tests."""

from __future__ import annotations

import unittest

from spell_sync.application.reports import OperationOutcome, PullExecution
from spell_sync.cli_options import CliOptions
from spell_sync.exit_codes import ExitCode
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.dashboard import DashboardScreen
from spell_sync.tui.screens.pull_screen import PullScreen
from tests.tui.fake_service import fake_service, sample_pull_preview
from tests.tui.test_helpers import wait_for_text


class TestPullFlow(unittest.IsolatedAsyncioTestCase):
    async def test_preview_fields_and_refresh(self):
        service = fake_service()
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.click("#btn-pull")
            content = await wait_for_text(pilot, "#pull-content", "custom diction")
            text = str(content.render())
            self.assertIn("17 words were found in application custom dictionaries", text)
            self.assertIn("Sources ready: 2", text)
            self.assertIn("Sources skipped: 1", text)
            await pilot.click("#btn-refresh")
            await wait_for_text(pilot, "#pull-content", "Plan id: pull-")
            self.assertGreaterEqual(service.pull_counter, 2)

    async def test_confirmation_and_success_report(self):
        service = fake_service()
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(PullScreen(controller))
            await wait_for_text(pilot, "#pull-content", "custom diction")
            await pilot.click("#btn-run")
            await wait_for_text(pilot, "#confirm-summary", "Add 17 words")
            await pilot.click("#btn-run")
            await wait_for_text(pilot, "#report-content", "Pull completed")
            self.assertEqual(service.execute_pull_calls, 1)

    async def test_cancel_before_execution(self):
        service = fake_service()
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(PullScreen(controller))
            await wait_for_text(pilot, "#pull-content", "custom diction")
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
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(PullScreen(controller))
            await wait_for_text(pilot, "#pull-content", "custom diction")
            await pilot.click("#btn-run")
            await wait_for_text(pilot, "#confirm-summary", "Add 17 words")
            await pilot.click("#btn-run")
            await wait_for_text(pilot, "#report-content", "Pull failed")

    async def test_back_navigation(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.click("#btn-pull")
            await wait_for_text(pilot, "#pull-content", "custom diction")
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_double_run_guard(self):
        service = fake_service()
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            screen = PullScreen(controller)
            app.push_screen(screen)
            await wait_for_text(pilot, "#pull-content", "custom diction")
            screen._starting = True
            screen.action_run_pull()
            self.assertEqual(service.execute_pull_calls, 0)


if __name__ == "__main__":
    unittest.main()
