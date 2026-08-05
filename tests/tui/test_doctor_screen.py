"""Doctor screen headless tests."""

from __future__ import annotations

import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from textual.widgets import DataTable

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
            await wait_for_text(pilot, "#doctor-summary", "blocking issues")
            table = app.screen.query_one("#doctor-table", DataTable)
            self.assertEqual(table.row_count, 3)
            joined = " | ".join(
                " ".join(str(cell) for cell in table.get_row_at(i)) for i in range(table.row_count)
            )
            self.assertIn("Configuration", joined)
            self.assertIn("Passed", joined)
            self.assertIn("Warning", joined)
            self.assertIn("Failed", joined)
            self.assertIn("Run recover", joined)

    async def test_rerun_and_back(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(DoctorScreen(controller))
            await wait_for_text(pilot, "#doctor-summary", "Doctor")
            await pilot.click("#btn-run-doctor")
            await wait_for_text(pilot, "#doctor-summary", "Doctor")
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_controlled_service_failure(self):
        doctor = DoctorSnapshot(checks=(), has_errors=True, load_error="Doctor failed.")
        controller = TuiController(fake_service(doctor=doctor), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(DoctorScreen(controller))
            content = await wait_for_text(pilot, "#doctor-summary", "Doctor failed")
            self.assertNotIn("Traceback", str(content.render()))

    async def test_export_support_report_success(self):
        controller = TuiController(fake_service(), CliOptions())
        controller.export_support_report = MagicMock(  # type: ignore[method-assign]
            return_value=Path("/tmp/support-reports/support-report-test.json")
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(DoctorScreen(controller))
            await wait_for_text(pilot, "#doctor-summary", "Doctor")
            await pilot.click("#btn-export-support")
            status = await wait_for_text(pilot, "#doctor-export-status", "Report saved")
            self.assertIn("Report saved", str(status.render()))
            controller.export_support_report.assert_called_once()

    async def test_export_support_report_collision(self):
        controller = TuiController(fake_service(), CliOptions())
        controller.export_support_report = MagicMock(  # type: ignore[method-assign]
            side_effect=FileExistsError("exists")
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(DoctorScreen(controller))
            await wait_for_text(pilot, "#doctor-summary", "Doctor")
            await pilot.click("#btn-export-support")
            await wait_for_text(pilot, "#doctor-export-status", "exists")

    async def test_export_support_report_generic_failure(self):
        controller = TuiController(fake_service(), CliOptions())
        controller.export_support_report = MagicMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("fail")
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(DoctorScreen(controller))
            await wait_for_text(pilot, "#doctor-summary", "Doctor")
            await pilot.click("#btn-export-support")
            await wait_for_text(pilot, "#doctor-export-status", "could not be exported")

    async def test_export_support_report_disables_button_while_running(self):
        from textual.widgets import Button

        controller = TuiController(fake_service(), CliOptions())
        release = threading.Event()

        def slow_export(**kwargs: object) -> Path:
            # Block until the test observes the disabled button (deterministic under CI load).
            assert release.wait(timeout=2.0)
            return Path("/tmp/support-reports/support-report-test.json")

        controller.export_support_report = MagicMock(side_effect=slow_export)  # type: ignore[method-assign]
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(DoctorScreen(controller))
            await wait_for_text(pilot, "#doctor-summary", "Doctor")
            await pilot.click("#btn-export-support")
            screen = app.screen
            assert isinstance(screen, DoctorScreen)
            btn = screen.query_one("#btn-export-support", Button)
            for _ in range(50):
                if btn.disabled:
                    break
                await pilot.pause()
            self.assertTrue(btn.disabled)
            release.set()
            await wait_for_text(pilot, "#doctor-export-status", "Report saved")
            self.assertFalse(btn.disabled)
            controller.export_support_report.assert_called_once()

    async def test_export_support_report_ignores_repeated_click(self):
        controller = TuiController(fake_service(), CliOptions())

        def slow_export(**kwargs: object) -> Path:
            time.sleep(0.3)
            return Path("/tmp/support-reports/support-report-test.json")

        controller.export_support_report = MagicMock(side_effect=slow_export)  # type: ignore[method-assign]
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(DoctorScreen(controller))
            await wait_for_text(pilot, "#doctor-summary", "Doctor")
            await pilot.click("#btn-export-support")
            await pilot.click("#btn-export-support")
            await wait_for_text(pilot, "#doctor-export-status", "Report saved")
            self.assertEqual(controller.export_support_report.call_count, 1)

    async def test_export_support_report_ignores_stale_result(self):
        controller = TuiController(fake_service(), CliOptions())
        completed = threading.Event()

        def slow_export(**kwargs: object) -> Path:
            completed.wait(timeout=1)
            return Path("/tmp/support-reports/support-report-test.json")

        controller.export_support_report = MagicMock(side_effect=slow_export)  # type: ignore[method-assign]
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(DoctorScreen(controller))
            await wait_for_text(pilot, "#doctor-summary", "Doctor")
            await pilot.click("#btn-export-support")
            await pilot.press("escape")
            completed.set()
            await pilot.pause(0.1)
            self.assertIsInstance(app.screen, DashboardScreen)


if __name__ == "__main__":
    unittest.main()
