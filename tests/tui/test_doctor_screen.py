"""Doctor screen headless tests."""

from __future__ import annotations

import unittest

from spell_sync.application.reports import DoctorCheckView, DoctorSnapshot
from spell_sync.cli_options import CliOptions
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.dashboard import DashboardScreen
from spell_sync.tui.screens.doctor_screen import DoctorScreen
from tests.tui.fake_service import fake_service, sample_doctor
from tests.tui.test_helpers import wait_for_text


class TestDoctorScreen(unittest.IsolatedAsyncioTestCase):
    async def test_passed_warning_failed_grouping(self):
        doctor = sample_doctor(
            checks=(
                DoctorCheckView(
                    group="Configuration",
                    level="passed",
                    title="Config valid",
                    detail="spell-sync.toml is valid.",
                ),
                DoctorCheckView(
                    group="Wordlist",
                    level="warning",
                    title="Wordlist empty",
                    detail="No words yet.",
                    suggested_action="Add words",
                ),
                DoctorCheckView(
                    group="Transaction state",
                    level="failed",
                    title="Journal corrupt",
                    detail="Cannot parse journal.",
                    suggested_action="Run recover",
                ),
            ),
            has_errors=True,
        )
        controller = TuiController(fake_service(doctor=doctor), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(DoctorScreen(controller))
            content = await wait_for_text(pilot, "#doctor-content", "Configuration")
            text = str(content.render())
            self.assertIn("✓ Passed", text)
            self.assertIn("! Warning", text)
            self.assertIn("× Failed", text)
            self.assertIn("Action: Run recover", text)

    async def test_rerun_and_back(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(DoctorScreen(controller))
            await wait_for_text(pilot, "#doctor-content", "Doctor")
            await pilot.click("#btn-run-doctor")
            await wait_for_text(pilot, "#doctor-content", "Doctor")
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_controlled_service_failure(self):
        doctor = DoctorSnapshot(checks=(), has_errors=True, load_error="Doctor failed.")
        controller = TuiController(fake_service(doctor=doctor), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(DoctorScreen(controller))
            content = await wait_for_text(pilot, "#doctor-content", "Doctor failed")
            self.assertNotIn("Traceback", str(content.render()))

    async def test_export_support_report(self):
        from pathlib import Path
        from unittest.mock import MagicMock

        controller = TuiController(fake_service(), CliOptions())
        controller.export_support_report = MagicMock(  # type: ignore[method-assign]
            return_value=Path("/tmp/support-reports/support-report-test.json")
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(DoctorScreen(controller))
            await wait_for_text(pilot, "#doctor-content", "Doctor")
            await pilot.click("#btn-export-support")
            status = await wait_for_text(pilot, "#doctor-export-status", "Report saved")
            self.assertIn("Report saved", str(status.render()))
            controller.export_support_report.assert_called_once()


if __name__ == "__main__":
    unittest.main()
