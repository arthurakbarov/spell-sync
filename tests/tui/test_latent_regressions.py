"""Regressions for latent bugs found in recent TUI polish arcs."""

import time
import unittest
from unittest.mock import MagicMock

from spell_sync.application.reports import OperationOutcome, OperationReport
from spell_sync.cli_options import CliOptions
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.dashboard import DashboardScreen
from spell_sync.tui.screens.recovery_screen import RecoveryScreen
from spell_sync.tui.screens.report_screen import ReportScreen
from spell_sync.tui.screens.setup_targets_screen import SetupTargetsScreen
from tests.tui.fake_service import fake_service, sample_recovery_preview
from tests.tui.test_helpers import wait_for_text


class TestLatentRegressions(unittest.IsolatedAsyncioTestCase):
    async def test_wait_for_text_fails_closed_on_timeout(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            with self.assertRaises(AssertionError) as ctx:
                await wait_for_text(
                    pilot, "#dashboard-summary", "this-text-never-appears", max_pauses=2
                )
            self.assertIn("Timed out", str(ctx.exception))

    async def test_setup_report_with_warnings_returns_to_dashboard(self):
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
            # Simulate wizard stack with no dashboard underneath.
            app.push_screen(ReportScreen(controller, report))
            await wait_for_text(pilot, "#report-content", "Project created")
            await pilot.click("#btn-dashboard")
            summary = await wait_for_text(pilot, "#dashboard-summary", "Ready")
            self.assertIsInstance(app.screen, DashboardScreen)
            self.assertNotIn("Loading", str(summary.render()))

    async def test_report_open_details_changes_content(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        report = OperationReport(
            operation="push",
            outcome=OperationOutcome.COMPLETED,
            title="Update my apps finished",
            summary="All good",
            details=("detail-line-unique",),
        )
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(ReportScreen(controller, report))
            content = await wait_for_text(pilot, "#report-content", "Update my apps finished")
            before = str(content.render())
            self.assertNotIn("detail-line-unique", before)
            await pilot.click("#btn-details")
            await pilot.pause()
            after = str(content.render())
            self.assertIn("detail-line-unique", after)
            self.assertEqual(str(app.screen.query_one("#btn-details").label), "Hide details")

    async def test_recovery_refresh_completes_via_worker_callback(self):
        preview = sample_recovery_preview()
        service = fake_service(recovery_preview=preview)
        calls = {"n": 0}
        real = service.inspect_recovery

        def slow_inspect(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] > 1:
                time.sleep(0.15)
            return real(*args, **kwargs)

        service.inspect_recovery = slow_inspect  # type: ignore[method-assign]
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(RecoveryScreen(controller))
            await wait_for_text(pilot, "#recovery-content", "Recover")
            app.screen.refresh_preview()
            content = await wait_for_text(pilot, "#recovery-content", "Recover", max_pauses=40)
            self.assertNotIn("Loading", str(content.render()))

    async def test_empty_applications_list_is_visible(self):
        controller = TuiController(fake_service(), CliOptions())
        controller.setup_target_discovery = MagicMock(  # type: ignore[method-assign]
            return_value=type("D", (), {"targets": ()})()
        )
        controller.setup_selection = MagicMock(  # type: ignore[method-assign]
            return_value=type("S", (), {"selected_target_ids": frozenset()})()
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupTargetsScreen(controller, "wordlist ok"))
            empty = await wait_for_text(pilot, ".setup-targets-empty", "No application")
            self.assertTrue(empty.display)


if __name__ == "__main__":
    unittest.main()
