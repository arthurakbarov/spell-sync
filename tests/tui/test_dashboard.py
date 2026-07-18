"""Dashboard screen headless tests."""

from __future__ import annotations

import unittest

from spell_sync.application.reports import DashboardIssue, DashboardSeverity
from spell_sync.cli_options import CliOptions
from spell_sync.exit_codes import ExitCode
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from tests.tui.fake_service import fake_service
from tests.tui.test_helpers import wait_for_text


class TestDashboardScreen(unittest.IsolatedAsyncioTestCase):
    async def test_ready_state(self):
        controller = TuiController(fake_service(severity=DashboardSeverity.READY), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            summary = await wait_for_text(pilot, "#dashboard-summary", "Ready")
            self.assertIn("Targets enabled: 2", str(summary.render()))

    async def test_warning_state(self):
        issues = (
            DashboardIssue(
                code="empty_wordlist",
                severity=DashboardSeverity.WARNING,
                title="Wordlist is empty",
                detail="Push will abort.",
            ),
        )
        controller = TuiController(
            fake_service(severity=DashboardSeverity.WARNING, issues=issues),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            summary = await wait_for_text(pilot, "#dashboard-summary", "Attention")
            self.assertIn("Attention required", str(summary.render()))

    async def test_invalid_config_blocked(self):
        controller = TuiController(fake_service(config_valid=False), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Wordlist")

    async def test_pending_recovery(self):
        controller = TuiController(fake_service(pending_recovery=True), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            summary = await wait_for_text(pilot, "#dashboard-summary", "Pending recovery")
            self.assertIn("Pending recovery: Yes", str(summary.render()))

    async def test_unreadable_wordlist(self):
        controller = TuiController(
            fake_service(wordlist_error=ExitCode.PUSH_ABORT),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Wordlist")

    async def test_blocked_issue_list(self):
        issues = (
            DashboardIssue(
                code="operation_lock",
                severity=DashboardSeverity.BLOCKED,
                title="Operation lock active",
                detail="pid 99",
            ),
        )
        controller = TuiController(
            fake_service(severity=DashboardSeverity.BLOCKED, issues=issues),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            issues_widget = await wait_for_text(pilot, "#dashboard-issues", "Operation lock")
            self.assertIn("Operation lock active", str(issues_widget.render()))

    async def test_refresh_hotkey(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.press("r")
            await wait_for_text(pilot, "#dashboard-summary", "Ready")

    async def test_open_doctor(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.click("#btn-doctor")
            await pilot.pause()
            from spell_sync.tui.screens.doctor_screen import DoctorScreen

            self.assertIsInstance(app.screen, DoctorScreen)


if __name__ == "__main__":
    unittest.main()
