"""Coverage for Phase 5 recovery screens and service paths."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from textual.widgets import Button, Input
from textual.worker import WorkerState

from spell_sync.application.reports import RecoveryStatus
from spell_sync.application.requests import ProjectRef
from spell_sync.cli_options import CliOptions
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.operation_screen import OperationScreen
from spell_sync.tui.screens.recovery_confirm_screen import RecoveryConfirmScreen
from spell_sync.tui.screens.recovery_screen import RecoveryScreen
from tests.tui.fake_service import fake_service, sample_recovery_preview
from tests.tui.test_helpers import wait_for_text


class TestPhase5Coverage(unittest.IsolatedAsyncioTestCase):
    async def test_recovery_mount_inspection_failure(self):
        service = fake_service(pending_recovery=True)
        service.raise_on_inspect = RuntimeError("boom")
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(RecoveryScreen(controller))
            await wait_for_text(pilot, "#recovery-content", "inspection failed")

    async def test_recovery_refresh_and_discard_flow(self):
        preview = sample_recovery_preview(can_discard=True, can_recover=False)
        service = fake_service(pending_recovery=True, recovery_preview=preview)
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(RecoveryScreen(controller))
            await wait_for_text(pilot, "#recovery-content", "Recoverable files")
            await pilot.click("#btn-refresh")
            await wait_for_text(pilot, "#recovery-content", "Recoverable files")
            await pilot.click("#btn-discard")
            await wait_for_text(pilot, "#confirm-summary", "DISCARD")
            screen = app.screen
            assert isinstance(screen, RecoveryConfirmScreen)
            screen.query_one("#confirm-input", Input).value = "DISCARD"
            screen.on_input_changed(Input.Changed(Input(), "DISCARD"))
            await pilot.click("#btn-run")
            await wait_for_text(pilot, "#report-content", "discarded")

    async def test_recovery_cleanup_pending_labels(self):
        preview = sample_recovery_preview(
            status=RecoveryStatus.COMPLETED_CLEANUP_PENDING,
            can_recover=False,
            can_cleanup=True,
            can_discard=True,
            detail="Only cleanup is required.",
        )
        controller = TuiController(
            fake_service(pending_recovery=True, recovery_preview=preview),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(RecoveryScreen(controller))
            await wait_for_text(pilot, "#recovery-content", "Only cleanup is required.")
            recover = app.screen.query_one("#btn-recover", Button)
            self.assertEqual(recover.label, "Clean up artifacts")

    async def test_recovery_view_details_and_back(self):
        preview = sample_recovery_preview(
            detail="Pending rollback",
            warnings=("Automatic rollback was incomplete.",),
        )
        controller = TuiController(
            fake_service(pending_recovery=True, recovery_preview=preview),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(RecoveryScreen(controller))
            await wait_for_text(pilot, "#recovery-content", "Automatic rollback")
            await pilot.click("#btn-details")
            await pilot.press("escape")
            await pilot.pause()

    async def test_recovery_confirm_cleanup_and_cancel(self):
        preview = sample_recovery_preview(
            status=RecoveryStatus.COMPLETED_CLEANUP_PENDING,
            can_cleanup=True,
        )
        controller = TuiController(fake_service(recovery_preview=preview), CliOptions())
        controller.set_active_recovery_preview(preview)
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(RecoveryConfirmScreen(controller, preview, "cleanup"))
            await wait_for_text(pilot, "#confirm-summary", "Only cleanup is required.")
            await pilot.click("#btn-cancel")
            await pilot.pause()

    async def test_recovery_confirm_rejects_bad_preview(self):
        controller = TuiController(fake_service(), CliOptions())
        preview = sample_recovery_preview(preview_fingerprint="gone")
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(RecoveryConfirmScreen(controller, preview, "recover"))
            await wait_for_text(pilot, "#confirm-summary", "RECOVER")
            screen = app.screen
            assert isinstance(screen, RecoveryConfirmScreen)
            screen.query_one("#confirm-input", Input).value = "RECOVER"
            await pilot.click("#btn-run")
            await pilot.pause()

    async def test_recovery_refresh_success_and_details(self):
        preview = sample_recovery_preview(
            snapshot_directory="/tmp/snapshots",
            detail="Pending rollback",
        )
        service = fake_service(pending_recovery=True, recovery_preview=preview)
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(RecoveryScreen(controller))
            await wait_for_text(pilot, "#recovery-content", "Recoverable files")
            await pilot.click("#btn-refresh")
            await wait_for_text(pilot, "#recovery-content", "Recoverable files")
            screen = app.screen
            assert isinstance(screen, RecoveryScreen)
            screen.on_button_pressed(Button.Pressed(screen.query_one("#btn-details", Button)))
            await pilot.pause()

    async def test_recovery_confirm_cancel_and_discard_cancel(self):
        preview = sample_recovery_preview(can_discard=True)
        service = fake_service(pending_recovery=True, recovery_preview=preview)
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(RecoveryScreen(controller))
            await wait_for_text(pilot, "#recovery-content", "Recoverable files")
            await pilot.click("#btn-recover")
            await wait_for_text(pilot, "#confirm-summary", "RECOVER")
            await pilot.click("#btn-cancel")
            await pilot.pause()
            await pilot.click("#btn-discard")
            await wait_for_text(pilot, "#confirm-summary", "DISCARD")
            await pilot.click("#btn-cancel")
            await pilot.pause()

    async def test_recovery_worker_error_poll(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(RecoveryScreen(controller))
            screen = app.screen
            assert isinstance(screen, RecoveryScreen)
            screen._worker = MagicMock()
            screen._worker.state = WorkerState.ERROR
            screen._poll_recovery_worker()
            await wait_for_text(pilot, "#recovery-content", "unavailable")

    async def test_recovery_operation_worker(self):
        preview = sample_recovery_preview()
        service = fake_service(pending_recovery=True, recovery_preview=preview)
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(
                OperationScreen(controller, operation="recover", recovery_preview=preview)
            )
            await wait_for_text(pilot, "#report-content", "Recovery completed")
            self.assertEqual(service.execute_recovery_calls, 1)


if __name__ == "__main__":
    unittest.main()
