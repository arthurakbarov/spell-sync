"""Coverage for Phase 5 recovery screens and service paths."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from textual.widgets import Button, Input
from textual.worker import WorkerState

from spell_sync.application.reports import RecoveryStatus
from spell_sync.application.requests import ProjectRef
from spell_sync.cli_options import CliOptions
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.dashboard import DashboardScreen
from spell_sync.tui.screens.operation_screen import OperationScreen
from spell_sync.tui.screens.recovery_confirm_screen import RecoveryConfirmScreen
from spell_sync.tui.screens.recovery_screen import RecoveryScreen
from tests.tui.fake_service import fake_service, sample_recovery_preview
from tests.tui.test_helpers import wait_for_operation_report, wait_for_text


class TestPhase5Coverage(unittest.IsolatedAsyncioTestCase):
    async def test_recovery_refresh_and_discard_flow(self):
        preview = sample_recovery_preview(can_discard=True, can_recover=False)
        service = fake_service(pending_recovery=True, recovery_preview=preview)
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
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
            await wait_for_operation_report(pilot, "discarded")

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
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(RecoveryScreen(controller))
            await wait_for_text(pilot, "#recovery-content", "Only cleanup is required.")
            recover = app.screen.query_one("#btn-recover", Button)
            self.assertEqual(recover.label, "Clean up artifacts")

    async def test_recovery_confirm_rejects_bad_preview(self):
        controller = TuiController(fake_service(), CliOptions())
        preview = sample_recovery_preview(preview_fingerprint="gone")
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
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
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(RecoveryScreen(controller))
            await wait_for_text(pilot, "#recovery-content", "Recoverable files")
            await pilot.click("#btn-refresh")
            await wait_for_text(pilot, "#recovery-content", "Recoverable files")
            screen = app.screen
            assert isinstance(screen, RecoveryScreen)
            screen.on_button_pressed(Button.Pressed(screen.query_one("#btn-details", Button)))
            await pilot.pause()

    async def test_recovery_worker_error_poll(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
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
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(
                OperationScreen(controller, operation="recover", recovery_preview=preview)
            )
            await wait_for_operation_report(pilot, "Recovery completed")
            self.assertEqual(service.execute_recovery_calls, 1)

    async def test_recovery_inspection_and_confirm_paths(self):
        preview = sample_recovery_preview(can_discard=True)
        service = fake_service(pending_recovery=True, recovery_preview=preview)
        service.raise_on_inspect = RuntimeError("boom")
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(RecoveryScreen(controller))
            content = await wait_for_text(pilot, "#recovery-content", "inspection failed")
            self.assertIn("failed", str(content.render()).lower())

        service.raise_on_inspect = None
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(RecoveryScreen(controller))
            await wait_for_text(pilot, "#recovery-content", "Recoverable files")
            await pilot.click("#btn-details")
            await pilot.press("escape")
            app.push_screen(RecoveryScreen(controller))
            await wait_for_text(pilot, "#recovery-content", "Recoverable files")
            await pilot.click("#btn-discard")
            await wait_for_text(pilot, "#confirm-summary", "DISCARD")
            await pilot.click("#btn-cancel")
            await pilot.pause()
            cleanup = sample_recovery_preview(
                status=RecoveryStatus.COMPLETED_CLEANUP_PENDING,
                can_cleanup=True,
            )
            controller.set_active_recovery_preview(cleanup)
            app.push_screen(RecoveryConfirmScreen(controller, cleanup, "cleanup"))
            await wait_for_text(pilot, "#confirm-summary", "Only cleanup is required.")
            await pilot.click("#btn-cancel")
            await pilot.pause()
            self.assertIsInstance(app.screen, RecoveryScreen)

    async def test_recovery_run_recover_while_unmounted(self):
        preview = sample_recovery_preview()
        controller = TuiController(
            fake_service(pending_recovery=True, recovery_preview=preview),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(RecoveryScreen(controller))
            await wait_for_text(pilot, "#recovery-content", "Recoverable files")
            screen = app.screen
            assert isinstance(screen, RecoveryScreen)
            with patch.object(app, "push_screen") as push_screen:
                screen.action_run_recover()
                callback = push_screen.call_args.args[1]
                with patch.object(type(screen), "is_mounted", property(lambda self: False)):
                    callback(True)
            self.assertFalse(controller.mutation_active)

    async def test_recovery_warnings_and_back_button(self):
        preview = sample_recovery_preview(
            detail="Pending rollback",
            warnings=("Automatic rollback was incomplete.",),
        )
        controller = TuiController(
            fake_service(pending_recovery=True, recovery_preview=preview),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(RecoveryScreen(controller))
            content = await wait_for_text(pilot, "#recovery-content", "Automatic rollback")
            self.assertIn("Warnings:", str(content.render()))
            screen = app.screen
            assert isinstance(screen, RecoveryScreen)
            screen.on_button_pressed(
                type("E", (), {"button": type("B", (), {"id": "btn-back"})()})()
            )
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_recovery_confirm_launches_operation(self):
        preview = sample_recovery_preview()
        controller = TuiController(
            fake_service(pending_recovery=True, recovery_preview=preview),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(RecoveryScreen(controller))
            await wait_for_text(pilot, "#recovery-content", "Recoverable files")
            screen = app.screen
            assert isinstance(screen, RecoveryScreen)
            with patch.object(app, "push_screen") as push_screen:
                screen.action_run_recover()
                callback = push_screen.call_args.args[1]
                callback(True)
            pushed = push_screen.call_args.args[0]
            self.assertIsInstance(pushed, OperationScreen)


if __name__ == "__main__":
    unittest.main()
