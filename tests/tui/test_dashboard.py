"""Dashboard screen headless tests."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from spell_sync.application.reports import DashboardIssue, DashboardSeverity
from spell_sync.application.requests import ProjectRef
from spell_sync.cli_options import CliOptions
from spell_sync.exit_codes import ExitCode
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.dashboard import DashboardScreen
from spell_sync.tui.screens.doctor_screen import DoctorScreen
from spell_sync.tui.screens.logs_screen import LogsScreen
from spell_sync.tui.screens.review_update_screen import ReviewUpdateScreen
from tests.tui.fake_service import fake_service, sample_dashboard
from tests.tui.test_helpers import wait_for_text


class TestDashboardScreen(unittest.IsolatedAsyncioTestCase):
    async def test_ready_state(self):
        controller = TuiController(
            fake_service(
                severity=DashboardSeverity.READY,
                targets_ready=5,
                targets_needs_attention=1,
                targets_disabled=2,
            ),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            summary = await wait_for_text(pilot, "#dashboard-summary", "Ready")
            text = str(summary.render())
            self.assertIn("Canonical personal wordlist", text)
            self.assertIn("5 ready", text)
            self.assertIn("1 need attention", text)
            self.assertIn("2 disabled", text)
            self.assertNotIn("Preview", text)

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
            fake_service(
                severity=DashboardSeverity.WARNING,
                issues=issues,
                targets_needs_attention=1,
            ),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            summary = await wait_for_text(pilot, "#dashboard-summary", "Attention")
            self.assertIn("Attention required", str(summary.render()))
            issues_widget = await wait_for_text(pilot, "#dashboard-issues", "Wordlist is empty")
            self.assertIn("Wordlist is empty", str(issues_widget.render()))

    async def test_invalid_config_blocked(self):
        issues = (
            DashboardIssue(
                code="invalid_config",
                severity=DashboardSeverity.BLOCKED,
                title="Invalid configuration",
                detail="Missing dictionaries section.",
            ),
        )
        controller = TuiController(
            fake_service(
                config_valid=False,
                severity=DashboardSeverity.BLOCKED,
                issues=issues,
            ),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            banner = await wait_for_text(pilot, "#blocking-banner", "Configuration blocked")
            self.assertIn("Invalid configuration", str(banner.render()))
            self.assertTrue(app.screen.query_one("#btn-pull").disabled)
            self.assertTrue(app.screen.query_one("#btn-push").disabled)

    async def test_pending_recovery_with_issue(self):
        issues = (
            DashboardIssue(
                code="pending_recovery",
                severity=DashboardSeverity.BLOCKED,
                title="Pending recovery",
                detail="journal in progress",
            ),
        )
        controller = TuiController(
            fake_service(pending_recovery=True, issues=issues),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            banner = await wait_for_text(pilot, "#blocking-banner", "Pending recovery")
            self.assertIn("unfinished push journal", str(banner.render()).lower())

    async def test_pending_recovery(self):
        controller = TuiController(fake_service(pending_recovery=True), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            banner = await wait_for_text(pilot, "#blocking-banner", "Pending recovery")
            self.assertIn("Pending recovery", str(banner.render()))
            self.assertIn("unfinished push journal", str(banner.render()))
            recovery_btn = app.screen.query_one("#btn-recovery")
            self.assertFalse(recovery_btn.disabled)
            self.assertEqual(recovery_btn.variant, "primary")
            self.assertTrue(app.screen.query_one("#btn-pull").disabled)
            self.assertTrue(app.screen.query_one("#btn-push").disabled)
            self.assertTrue(app.screen.query_one("#btn-review-update").disabled)

    async def test_unreadable_wordlist(self):
        issues = (
            DashboardIssue(
                code="unreadable_wordlist",
                severity=DashboardSeverity.BLOCKED,
                title="Wordlist unreadable",
                detail="Permission denied.",
            ),
        )
        controller = TuiController(
            fake_service(
                wordlist_error=ExitCode.PUSH_ABORT,
                severity=DashboardSeverity.BLOCKED,
                issues=issues,
            ),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            banner = await wait_for_text(pilot, "#blocking-banner", "Wordlist blocked")
            self.assertIn("Wordlist unreadable", str(banner.render()))

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

    async def test_no_duplicate_preview_button(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            screen = app.screen
            assert isinstance(screen, DashboardScreen)
            with self.assertRaises(Exception):
                screen.query_one("#btn-preview")

    async def test_push_opens_preview(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.click("#btn-push")
            await pilot.pause()
            from spell_sync.tui.screens.preview_screen import PreviewScreen

            self.assertIsInstance(app.screen, PreviewScreen)

    async def test_open_review_update_start(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.click("#btn-review-update")
            await pilot.pause()
            self.assertIsInstance(app.screen, ReviewUpdateScreen)
            body = await wait_for_text(pilot, "#review-body", "Start review")
            self.assertIn("Nothing changes without confirmation", str(body.render()))
            await pilot.click("#btn-back")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_open_health(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.press("h")
            await pilot.pause()
            self.assertIsInstance(app.screen, DoctorScreen)

    async def test_open_history(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            screen = app.screen
            assert isinstance(screen, DashboardScreen)
            screen.on_button_pressed(SimpleNamespace(button=SimpleNamespace(id="btn-history")))
            await pilot.pause()
            self.assertIsInstance(app.screen, LogsScreen)

    async def test_open_targets(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.click("#btn-targets")
            await pilot.pause()
            from spell_sync.tui.screens.target_settings_screen import TargetSettingsScreen

            self.assertIsInstance(app.screen, TargetSettingsScreen)

    async def test_last_operation_summary(self):
        controller = TuiController(
            fake_service(last_operation_summary="Last: Push — 2 targets updated"),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            summary = await wait_for_text(pilot, "#dashboard-summary", "Last: Push")
            self.assertIn("2 targets updated", str(summary.render()))

    async def test_refresh_hotkey(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.press("r")
            await wait_for_text(pilot, "#dashboard-summary", "Ready")

    async def test_keyboard_navigation(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.press("s")
            await pilot.pause()
            from spell_sync.tui.screens.status_screen import StatusScreen

            self.assertIsInstance(app.screen, StatusScreen)

    async def test_status_button_opens_status_screen(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            screen = app.screen
            assert isinstance(screen, DashboardScreen)
            screen.on_button_pressed(SimpleNamespace(button=SimpleNamespace(id="btn-status")))
            await pilot.pause()
            from spell_sync.tui.screens.status_screen import StatusScreen

            self.assertIsInstance(app.screen, StatusScreen)

    async def test_layout_warning_at_80x24(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(80, 24)):
            warning = app.screen.query_one("#narrow-warning")
            self.assertEqual(str(warning.render()), "")

    async def test_layout_warning_below_minimum(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(60, 20)) as pilot:
            warning = await wait_for_text(pilot, "#narrow-warning", "80x24")
            self.assertIn("80x24", str(warning.render()))

    async def test_recovery_navigation(self):
        controller = TuiController(fake_service(pending_recovery=True), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            await wait_for_text(pilot, "#blocking-banner", "Recovery required")
            await pilot.click("#btn-recovery")
            await pilot.pause()
            from spell_sync.tui.screens.recovery_screen import RecoveryScreen

            self.assertIsInstance(app.screen, RecoveryScreen)

    async def test_health_and_history_available_during_recovery(self):
        controller = TuiController(fake_service(pending_recovery=True), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await wait_for_text(pilot, "#blocking-banner", "Recovery required")
            self.assertFalse(app.screen.query_one("#btn-health").disabled)
            self.assertFalse(app.screen.query_one("#btn-history").disabled)

    async def test_home_wordlist_path_display(self):
        home_wordlist = str(Path.home() / "spell-words" / "wordlist.txt")
        service = fake_service()
        service.dashboard_state = sample_dashboard(wordlist_path=home_wordlist)
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            summary = await wait_for_text(pilot, "#dashboard-summary", "~/")
            self.assertIn("~/spell-words/wordlist.txt", str(summary.render()))

    async def test_no_targets_configured_message(self):
        controller = TuiController(
            fake_service(
                targets_ready=0,
                targets_needs_attention=0,
                targets_disabled=0,
                targets_unavailable=0,
            ),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            summary = await wait_for_text(
                pilot,
                "#dashboard-summary",
                "No application targets configured",
            )
            self.assertIn("No application targets configured", str(summary.render()))

    async def test_unavailable_targets_display(self):
        controller = TuiController(
            fake_service(targets_unavailable=2),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            summary = await wait_for_text(pilot, "#dashboard-summary", "2 unavailable")
            self.assertIn("2 unavailable", str(summary.render()))

    async def test_blocked_write_actions_notify(self):
        controller = TuiController(
            fake_service(severity=DashboardSeverity.BLOCKED, pending_recovery=True),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await wait_for_text(pilot, "#blocking-banner", "Recovery required")
            screen = app.screen
            assert isinstance(screen, DashboardScreen)
            screen.action_open_review_update()
            screen.action_open_preview()
            await pilot.pause()

    async def test_corrupt_journal_banner(self):
        issues = (
            DashboardIssue(
                code="corrupt_journal",
                severity=DashboardSeverity.BLOCKED,
                title="Corrupt journal",
                detail="bad",
            ),
        )
        controller = TuiController(
            fake_service(severity=DashboardSeverity.BLOCKED, issues=issues),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            banner = await wait_for_text(pilot, "#blocking-banner", "Corrupt push journal")
            self.assertIn("Corrupt push journal", str(banner.render()))


if __name__ == "__main__":
    unittest.main()
