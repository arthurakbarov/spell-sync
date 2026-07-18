"""Coverage for Phase 4 mutation screens and edge paths."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from textual.widgets import Input
from textual.worker import WorkerState

from spell_sync.application.events import EventLevel, OperationEvent, OperationKind
from spell_sync.application.reports import (
    OperationOutcome,
    OperationReport,
    TargetUpdateReport,
)
from spell_sync.cli_options import CliOptions
from spell_sync.exit_codes import ExitCode
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.operation_screen import OperationScreen
from spell_sync.tui.screens.preview_screen import PreviewScreen
from spell_sync.tui.screens.pull_confirm_screen import PullConfirmScreen
from spell_sync.tui.screens.pull_screen import PullScreen
from spell_sync.tui.screens.push_confirm_screen import PushConfirmScreen
from spell_sync.tui.screens.report_screen import ReportScreen
from tests.tui.fake_service import fake_service, sample_preview, sample_pull_preview
from tests.tui.test_helpers import wait_for_text


class TestPhase4Coverage(unittest.IsolatedAsyncioTestCase):
    async def test_operation_event_and_cancel_policy(self):
        service = fake_service()
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            preview = sample_pull_preview()
            screen = OperationScreen(controller, operation="pull", pull_preview=preview)
            app.push_screen(screen)
            await wait_for_text(pilot, "#report-content", "Pull completed")
            await pilot.click("#btn-dashboard")
            await wait_for_text(pilot, "#dashboard-summary", "Ready")

    async def test_operation_blocked_second_mutation(self):
        service = fake_service()
        controller = TuiController(service, CliOptions())
        controller.begin_mutation()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            screen = OperationScreen(
                controller,
                operation="pull",
                pull_preview=sample_pull_preview(),
            )
            app.push_screen(screen)
            await wait_for_text(pilot, "#operation-stages", "already running")
            screen.action_safe_back()
            screen.action_safe_quit()

    async def test_operation_apply_event_branches(self):
        service = fake_service()
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            screen = OperationScreen(
                controller,
                operation="push",
                push_preview=sample_preview(removals=0),
            )
            app.push_screen(screen)
            await pilot.pause()
            screen._apply_event(
                OperationEvent(
                    OperationKind.PUSH,
                    "rolling_back",
                    "rolling",
                    level=EventLevel.WARNING,
                    target="chrome",
                )
            )
            screen._apply_event(
                OperationEvent(
                    OperationKind.PUSH,
                    "finalizing",
                    "done",
                    level=EventLevel.SUCCESS,
                    completed=1,
                    total=2,
                )
            )
            screen._finish_failed("boom")
            await pilot.pause()

    async def test_report_details_rebuild_and_quit(self):
        service = fake_service()
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        report = OperationReport(
            operation="push",
            outcome=OperationOutcome.STOPPED_SAFELY,
            title="Push stopped safely",
            summary="conflict",
            details=("detail",),
            warnings=("warn",),
            conflict_target="chrome",
            plan_identifier="p1",
            target_updates=(TargetUpdateReport("chrome", 1, 0, "Ready"),),
            recovery_required=False,
        )
        async with app.run_test(size=(100, 36)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            app.push_screen(ReportScreen(controller, report))
            await wait_for_text(pilot, "#report-content", "stopped safely")
            await pilot.click("#btn-details")
            await pilot.pause()
            await pilot.click("#btn-rebuild")
            await wait_for_text(pilot, "#preview-content", "Plan id")

    async def test_report_recovery_required(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        report = OperationReport(
            operation="push",
            outcome=OperationOutcome.RECOVERY_REQUIRED,
            title="Push requires recovery",
            summary="incomplete",
            recovery_required=True,
        )
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(ReportScreen(controller, report))
            content = await wait_for_text(pilot, "#report-content", "Recovery is required")
            self.assertIn("Recovery is required", str(content.render()))

    async def test_push_confirm_invalid_preview(self):
        service = fake_service()
        controller = TuiController(service, CliOptions())
        preview = sample_preview(removals=0, plan_identifier="gone")
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(PushConfirmScreen(controller, preview))
            await wait_for_text(pilot, "#confirm-summary", "additions")
            await pilot.click("#btn-run")
            await pilot.pause()
            self.assertEqual(service.execute_push_calls, 0)

    async def test_push_confirm_view_removals(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(PushConfirmScreen(controller, sample_preview()))
            await wait_for_text(pilot, "#confirm-summary", "Type PUSH")
            await pilot.click("#btn-view-removals")
            await pilot.pause()

    async def test_pull_confirm_invalid_preview(self):
        service = fake_service()
        controller = TuiController(service, CliOptions())
        preview = sample_pull_preview(plan_identifier="gone")
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(PullConfirmScreen(controller, preview))
            await wait_for_text(pilot, "#confirm-summary", "Add")
            await pilot.click("#btn-run")
            await pilot.pause()
            self.assertEqual(service.execute_pull_calls, 0)

    async def test_pull_screen_view_additions_and_error_preview(self):
        preview = sample_pull_preview(wordlist_error=ExitCode.PUSH_ABORT)
        service = fake_service(pull_preview=preview)
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(PullScreen(controller))
            await wait_for_text(pilot, "#pull-content", "unavailable")
            screen = app.screen
            assert isinstance(screen, PullScreen)
            screen._preview = sample_pull_preview()
            screen.action_view_additions()
            await pilot.pause()

    async def test_preview_continue_unavailable(self):
        preview = sample_preview(prepared=None, prepare_error=ExitCode.PUSH_ABORT)
        controller = TuiController(fake_service(preview=preview), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Plan blocked")
            screen = app.screen
            assert isinstance(screen, PreviewScreen)
            screen.action_continue_push()

    async def test_controller_writes_blocked(self):
        from spell_sync.application.reports import DashboardSeverity

        controller = TuiController(
            fake_service(severity=DashboardSeverity.BLOCKED, pending_recovery=True),
            CliOptions(),
        )
        self.assertTrue(controller.writes_blocked())

    async def test_typed_confirm_wrong_then_right(self):
        preview = sample_preview(plan_identifier="fixed")
        service = fake_service(preview=preview)
        service.load_push_preview = lambda opts: preview  # type: ignore[method-assign]
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Plan id")
            await pilot.click("#btn-continue-push")
            await wait_for_text(pilot, "#confirm-summary", "Type PUSH")
            screen = app.screen
            assert isinstance(screen, PushConfirmScreen)
            confirm_input = screen.query_one("#confirm-input", Input)
            confirm_input.value = "nope"
            screen.on_input_changed(Input.Changed(confirm_input, "nope"))
            await pilot.pause()
            self.assertTrue(screen.query_one("#btn-run").disabled)
            self.assertEqual(service.execute_push_calls, 0)
            confirm_input.value = "PUSH"
            screen.on_input_changed(Input.Changed(confirm_input, "PUSH"))
            await pilot.pause()
            await pilot.click("#btn-run")
            await wait_for_text(pilot, "#report-content", "Push completed")
            self.assertEqual(service.execute_push_calls, 1)

    async def test_operation_worker_poll_error(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            screen = OperationScreen(
                controller,
                operation="pull",
                pull_preview=sample_pull_preview(),
            )
            app.push_screen(screen)
            await pilot.pause()
            screen._worker = SimpleNamespace(state=WorkerState.ERROR, result=None)
            screen._poll_operation()
            await pilot.pause()

    async def test_operation_null_result_and_bindings(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            screen = OperationScreen(controller, operation="unknown")
            app.push_screen(screen)
            await wait_for_text(pilot, "#operation-stages", "no result")
            screen._finished = True
            screen.on_button_pressed(
                type("E", (), {"button": type("B", (), {"id": "btn-close"})()})()
            )
            screen.action_safe_back()
            screen._mutating = True
            screen._finished = False
            screen.action_safe_back()
            screen.action_safe_quit()

    async def test_operation_callback_paths(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            screen = OperationScreen(
                controller,
                operation="pull",
                pull_preview=sample_pull_preview(),
            )
            app.push_screen(screen)
            await pilot.pause()
            screen.on_execute_operation_worker_state_changed(
                SimpleNamespace(state=WorkerState.RUNNING, worker=None)
            )
            screen.on_execute_operation_worker_state_changed(
                SimpleNamespace(
                    state=WorkerState.ERROR,
                    worker=SimpleNamespace(result=None),
                )
            )
            await pilot.pause()

    async def test_quit_blocked_during_mutation(self):
        controller = TuiController(fake_service(), CliOptions())
        controller.begin_mutation()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            app.action_quit_app()
            await pilot.click("#btn-quit")
            await pilot.pause()
            self.assertTrue(controller.mutation_active)

    async def test_dashboard_pull_blocked_and_recovery_hint(self):
        from spell_sync.application.reports import DashboardSeverity
        from spell_sync.tui.screens.dashboard import DashboardScreen

        controller = TuiController(
            fake_service(severity=DashboardSeverity.BLOCKED, pending_recovery=True),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "blocked")
            screen = app.screen
            assert isinstance(screen, DashboardScreen)
            screen.action_open_pull()
            await pilot.click("#btn-recovery")
            await pilot.pause()

    async def test_pull_screen_refresh_and_run_guards(self):
        service = fake_service()
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(PullScreen(controller))
            await wait_for_text(pilot, "#pull-content", "New words")
            screen = app.screen
            assert isinstance(screen, PullScreen)
            await pilot.click("#btn-refresh")
            await wait_for_text(pilot, "#pull-content", "New words")
            screen._preview = None
            screen.action_run_pull()
            screen.action_view_additions()
            screen._preview = sample_pull_preview()
            controller.begin_mutation()
            screen.action_run_pull()
            controller.end_mutation()
            screen._worker = SimpleNamespace(state=WorkerState.ERROR, result=None)
            screen._poll_pull_worker()
            screen.on_load_pull_worker_state_changed(
                SimpleNamespace(state=WorkerState.RUNNING, worker=None)
            )
            screen.on_load_pull_worker_state_changed(
                SimpleNamespace(
                    state=WorkerState.ERROR,
                    worker=SimpleNamespace(result=None),
                )
            )
            screen.on_load_pull_worker_state_changed(
                SimpleNamespace(
                    state=WorkerState.SUCCESS,
                    worker=SimpleNamespace(result=sample_pull_preview()),
                )
            )
            await pilot.pause()

    async def test_pull_screen_mount_exception(self):
        service = fake_service()
        service.prepare_pull = lambda opts: (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore[method-assign]
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(PullScreen(controller))
            await wait_for_text(pilot, "#pull-content", "load failed")

    async def test_preview_poll_error_and_continue_cancel(self):
        preview = sample_preview(removals=0, plan_identifier="fixed")
        service = fake_service(preview=preview)
        service.load_push_preview = lambda opts: preview  # type: ignore[method-assign]
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Plan id")
            screen = app.screen
            assert isinstance(screen, PreviewScreen)
            screen._worker = SimpleNamespace(state=WorkerState.ERROR, result=None)
            screen._poll_preview_worker()
            await pilot.click("#btn-continue-push")
            await wait_for_text(pilot, "#confirm-summary", "additions")
            await pilot.click("#btn-cancel")
            await pilot.pause()

    async def test_push_confirm_cancel_and_prepared_mismatch(self):
        service = fake_service()
        controller = TuiController(service, CliOptions())
        preview = sample_preview(removals=0, plan_identifier="p1")
        other = sample_preview(removals=0, plan_identifier="p1")
        controller._active_push_preview = other
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(PushConfirmScreen(controller, preview))
            await wait_for_text(pilot, "#confirm-summary", "additions")
            await pilot.click("#btn-run")
            await pilot.pause()
            self.assertEqual(service.execute_push_calls, 0)
            app.push_screen(PushConfirmScreen(controller, preview))
            await wait_for_text(pilot, "#confirm-summary", "additions")
            await pilot.click("#btn-cancel")
            await pilot.pause()

    async def test_push_confirm_typed_guard_and_non_typed_input(self):
        controller = TuiController(fake_service(), CliOptions())
        preview = sample_preview(removals=0)
        controller._active_push_preview = preview
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            screen = PushConfirmScreen(controller, preview)
            app.push_screen(screen)
            await wait_for_text(pilot, "#confirm-summary", "additions")
            screen.on_input_changed(Input.Changed(Input(), "x"))
            typed = sample_preview(removals=2, plan_identifier="typed")
            controller._active_push_preview = typed
            screen2 = PushConfirmScreen(controller, typed)
            app.push_screen(screen2)
            await wait_for_text(pilot, "#confirm-summary", "Type PUSH")
            confirm_input = screen2.query_one("#confirm-input", Input)
            confirm_input.value = "no"
            await pilot.click("#btn-run")
            await pilot.pause()

    async def test_report_quit_and_details_recovery(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        report = OperationReport(
            operation="push",
            outcome=OperationOutcome.RECOVERY_REQUIRED,
            title="Push requires recovery",
            summary="incomplete",
            details=("meta",),
            warnings=("w",),
            recovery_required=True,
            conflict_target="chrome",
        )
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(ReportScreen(controller, report))
            await wait_for_text(pilot, "#report-content", "Recovery")
            await pilot.click("#btn-details")
            await pilot.pause()
            await pilot.click("#btn-quit")

    async def test_operation_unmounted_and_finished_guards(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            op2 = OperationScreen(controller, operation="unknown")
            app.push_screen(op2)
            await wait_for_text(pilot, "#operation-stages", "no result")
            op2._worker = None
            op2._poll_operation()
            op2._finished = False
            op2._worker = SimpleNamespace(state=WorkerState.ERROR, result=None)
            op2._poll_operation()
            with patch.object(type(op2), "is_mounted", property(lambda self: False)):
                op2._flush_events()
                op2._finished = False
                op2._complete_with_result(None)
            op2._finished = True
            op2._complete_with_result(None)
            op2.on_button_pressed(
                type(
                    "Pressed",
                    (),
                    {"button": type("B", (), {"id": "btn-other"})()},
                )()
            )
            await pilot.pause()

    async def test_operation_worker_success_callback(self):
        from spell_sync.application.reports import PullExecution

        service = fake_service()
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            op = OperationScreen(
                controller,
                operation="pull",
                pull_preview=sample_pull_preview(),
            )
            # Prevent auto worker from racing; drive callback manually.
            with patch.object(op, "execute_operation_worker", return_value=None):
                app.push_screen(op)
                await pilot.pause()
                controller.begin_mutation()
                op._finished = False
                execution = PullExecution(
                    preview=sample_pull_preview(),
                    result=(1, 2),
                    outcome=OperationOutcome.COMPLETED,
                    message="ok",
                )
                op.on_execute_operation_worker_state_changed(
                    SimpleNamespace(
                        state=WorkerState.SUCCESS,
                        worker=SimpleNamespace(result=execution),
                    )
                )
                await wait_for_text(pilot, "#report-content", "Pull completed")

    async def test_pull_worker_exception_and_token_mismatch(self):
        service = fake_service()
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(PullScreen(controller))
            await wait_for_text(pilot, "#pull-content", "New words")
            pull = app.screen
            assert isinstance(pull, PullScreen)
            await pilot.click("#btn-view-additions")
            await pilot.pause()
            app.pop_screen()
            with patch.object(controller, "prepare_pull", side_effect=RuntimeError("x")):
                err = PullScreen.load_pull_worker.__wrapped__(pull)
            self.assertEqual(err.plan_identifier, "error")
            pull._active_token = -1
            pull._worker = SimpleNamespace(
                state=WorkerState.SUCCESS,
                result=sample_pull_preview(),
            )
            pull._poll_pull_worker()
            pull.on_load_pull_worker_state_changed(
                SimpleNamespace(state=WorkerState.CANCELLED, worker=None)
            )
            pull._active_token = -1
            pull.on_load_pull_worker_state_changed(
                SimpleNamespace(
                    state=WorkerState.SUCCESS,
                    worker=SimpleNamespace(result=sample_pull_preview()),
                )
            )
            # Post-confirm callback when screen is unmounted (line 162).
            pull._preview = sample_pull_preview()
            pull._starting = False
            captured: list = []

            def _push_screen(screen, callback=None):
                if callback is not None:
                    captured.append(callback)

            with patch.object(pull.app, "push_screen", side_effect=_push_screen):
                pull.action_run_pull()
            self.assertTrue(captured)
            with patch.object(type(pull), "is_mounted", property(lambda self: False)):
                captured[0](True)
            await pilot.pause()

    async def test_preview_token_mismatch_and_unmounted_confirm(self):
        preview_obj = sample_preview(removals=0, plan_identifier="fixed")
        service = fake_service(preview=preview_obj)
        service.load_push_preview = lambda opts: preview_obj  # type: ignore[method-assign]
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Plan id")
            preview = app.screen
            assert isinstance(preview, PreviewScreen)
            preview._active_token = -1
            preview._worker = SimpleNamespace(
                state=WorkerState.SUCCESS,
                result=preview_obj,
            )
            preview._poll_preview_worker()

            def _capture(callback):
                with patch.object(type(preview), "is_mounted", property(lambda self: False)):
                    callback(True)

            with patch.object(
                preview.app, "push_screen", side_effect=lambda *a, **k: _capture(a[1])
            ):
                preview.action_continue_push()
            await pilot.pause()

    async def test_typed_confirm_rejects_wrong_text_on_click(self):
        from textual.widgets import Button

        controller = TuiController(fake_service(), CliOptions())
        typed = sample_preview(removals=2, plan_identifier="typed-reject")
        controller._active_push_preview = typed
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(PushConfirmScreen(controller, typed))
            await wait_for_text(pilot, "#confirm-summary", "Type PUSH")
            screen = app.screen
            assert isinstance(screen, PushConfirmScreen)
            screen.query_one("#confirm-input", Input).value = "push"
            run_btn = screen.query_one("#btn-run", Button)
            run_btn.disabled = False
            screen.on_button_pressed(Button.Pressed(run_btn))
            await pilot.pause()
            self.assertIsInstance(app.screen, PushConfirmScreen)

    async def test_report_stack_break_branches(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        report = OperationReport(
            operation="push",
            outcome=OperationOutcome.STOPPED_SAFELY,
            title="Push stopped safely",
            summary="conflict",
            conflict_target="chrome",
        )
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(ReportScreen(controller, report))
            await wait_for_text(pilot, "#report-content", "stopped")
            screen = app.screen
            assert isinstance(screen, ReportScreen)
            # Non-dashboard top screen with a single-item stack hits the break.
            with patch.object(type(app), "screen_stack", property(lambda self: [screen])):
                screen._rebuild_preview()
                screen.action_back_dashboard()
            await pilot.pause()


if __name__ == "__main__":
    unittest.main()
