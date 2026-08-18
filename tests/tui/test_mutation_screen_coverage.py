"""Coverage for mutation screens and edge paths."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from textual.widgets import Input
from textual.worker import WorkerState

from spell_sync.application.events import (
    EventId,
    EventSeverity,
    EventStage,
    OperationKind,
    PresentedEvent,
)
from spell_sync.application.reports import (
    OperationOutcome,
    OperationReport,
    TargetUpdateReport,
)
from spell_sync.application.requests import ProjectRef
from spell_sync.cli_options import CliOptions
from spell_sync.exit_codes import ExitCode
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.dashboard import DashboardScreen
from spell_sync.tui.screens.operation_screen import OperationScreen
from spell_sync.tui.screens.preview_screen import PreviewScreen
from spell_sync.tui.screens.pull_confirm_screen import PullConfirmScreen
from spell_sync.tui.screens.pull_screen import PullScreen
from spell_sync.tui.screens.push_confirm_screen import PushConfirmScreen
from spell_sync.tui.screens.report_screen import ReportScreen
from tests.tui.fake_service import fake_service, sample_preview, sample_pull_preview
from tests.tui.test_helpers import wait_for_operation_report, wait_for_text


class TestMutationScreenCoverage(unittest.IsolatedAsyncioTestCase):
    def test_operation_unmount_ends_mutation_when_unfinished(self) -> None:
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        screen = OperationScreen(
            controller,
            operation="pull",
            pull_preview=sample_pull_preview(),
        )
        self.assertTrue(controller.begin_mutation())
        screen._finished = False
        screen.on_unmount()
        self.assertFalse(controller.mutation_active)

    async def test_operation_blocked_when_mutation_active(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        controller.begin_mutation()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            screen = OperationScreen(
                controller,
                operation="pull",
                pull_preview=sample_pull_preview(),
            )
            app.push_screen(screen)
            await wait_for_text(pilot, "#operation-stages-table", "already running")
            self.assertTrue(screen._finished)

    async def test_operation_success_dismisses_to_report(self):
        from spell_sync.application.reports import PullExecution

        service = fake_service()
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            screen = OperationScreen(
                controller,
                operation="pull",
                pull_preview=sample_pull_preview(),
            )
            with patch.object(screen, "execute_operation_worker", return_value=None):
                app.push_screen(screen)
                await pilot.pause()
                execution = PullExecution(
                    preview=sample_pull_preview(),
                    result=(1, 2),
                    outcome=OperationOutcome.COMPLETED,
                    message="ok",
                )
                screen.on_execute_operation_worker_state_changed(
                    SimpleNamespace(
                        state=WorkerState.SUCCESS,
                        worker=SimpleNamespace(result=execution),
                    )
                )
                await pilot.pause()
                screen.on_key(SimpleNamespace(key="enter"))
                await pilot.pause()
                self.assertIsInstance(app.screen, ReportScreen)

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
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(ReportScreen(controller, report))
            await wait_for_text(pilot, "#report-content", "Push requires recovery")
            await pilot.click("#btn-details")
            content = await wait_for_text(
                pilot,
                "#report-content",
                "Open Finish interrupted update before another write operation",
            )
            self.assertIn("Rollback incomplete", str(content.render()))

    async def test_push_confirm_invalid_preview(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        preview = sample_preview(removals=0, plan_identifier="gone")
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PushConfirmScreen(controller, preview))
            await wait_for_text(pilot, "#confirm-summary", "additions")
            await pilot.click("#btn-run")
            await pilot.pause()
            self.assertEqual(service.execute_push_calls, 0)

    async def test_pull_confirm_invalid_preview(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        preview = sample_pull_preview(plan_identifier="gone")
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PullConfirmScreen(controller, preview))
            await wait_for_text(pilot, "#confirm-summary", "Add")
            await pilot.click("#btn-run")
            await pilot.pause()
            self.assertEqual(service.execute_pull_calls, 0)

    async def test_pull_screen_view_additions_and_error_preview(self):
        preview = sample_pull_preview(wordlist_error=ExitCode.PUSH_ABORT)
        service = fake_service(pull_preview=preview)
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PullScreen(controller))
            await wait_for_text(pilot, "#pull-summary", "unavailable")
            screen = app.screen
            assert isinstance(screen, PullScreen)
            screen._preview = sample_pull_preview()
            screen.action_view_additions()
            await pilot.pause()

    async def test_preview_continue_unavailable(self):
        preview = sample_preview(prepared=None, prepare_error=ExitCode.PUSH_ABORT)
        controller = TuiController(fake_service(preview=preview), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "unavailable")
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
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Words to add")
            await pilot.click("#btn-continue-push")
            await wait_for_text(pilot, "#confirm-summary", "Type REMOVE")
            screen = app.screen
            assert isinstance(screen, PushConfirmScreen)
            confirm_input = screen.query_one("#confirm-input", Input)
            confirm_input.value = "nope"
            screen.on_input_changed(Input.Changed(confirm_input, "nope"))
            await pilot.pause()
            self.assertTrue(screen.query_one("#btn-run").disabled)
            self.assertEqual(service.execute_push_calls, 0)
            confirm_input.value = "REMOVE"
            screen.on_input_changed(Input.Changed(confirm_input, "REMOVE"))
            await pilot.pause()
            await pilot.click("#btn-run")
            await wait_for_operation_report(pilot, "Update my apps completed")
            self.assertEqual(service.execute_push_calls, 1)

    async def test_quit_blocked_during_mutation(self):
        controller = TuiController(fake_service(), CliOptions())
        controller.begin_mutation()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            app.action_quit_app()
            screen = app.screen
            assert isinstance(screen, DashboardScreen)
            screen.on_button_pressed(SimpleNamespace(button=SimpleNamespace(id="btn-quit")))
            await pilot.pause()
            self.assertTrue(controller.mutation_active)

    async def test_dashboard_pull_blocked_and_recovery_hint(self):
        from spell_sync.application.reports import DashboardSeverity

        controller = TuiController(
            fake_service(severity=DashboardSeverity.BLOCKED, pending_recovery=True),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "blocked")
            screen = app.screen
            assert isinstance(screen, DashboardScreen)
            screen.action_open_pull()
            await pilot.click("#btn-recovery")
            await pilot.pause()

    async def test_pull_screen_refresh_and_run_guards(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PullScreen(controller))
            await wait_for_text(pilot, "#pull-summary", "custom diction")
            screen = app.screen
            assert isinstance(screen, PullScreen)
            await pilot.click("#btn-refresh")
            await wait_for_text(pilot, "#pull-summary", "custom diction")
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

    async def test_preview_poll_error_and_continue_cancel(self):
        preview = sample_preview(removals=0, plan_identifier="fixed")
        service = fake_service(preview=preview)
        service.load_push_preview = lambda opts: preview  # type: ignore[method-assign]
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Words to add")
            screen = app.screen
            assert isinstance(screen, PreviewScreen)
            screen._worker = SimpleNamespace(state=WorkerState.ERROR, result=None)
            screen._poll_preview_worker()
            await pilot.pause()
            # Keep the successful mount preview executable so Continue still opens confirm.
            screen._preview = preview
            screen._update_continue_button(preview)
            await pilot.click("#btn-continue-push")
            await wait_for_text(pilot, "#confirm-summary", "additions")
            await pilot.click("#btn-cancel")
            await pilot.pause()

    async def test_push_confirm_cancel_and_prepared_mismatch(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        preview = sample_preview(removals=0, plan_identifier="p1")
        other = sample_preview(removals=0, plan_identifier="p1")
        controller._active_push_preview = other
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PushConfirmScreen(controller, preview))
            await wait_for_text(pilot, "#confirm-summary", "additions")
            await pilot.click("#btn-run")
            await pilot.pause()
            self.assertEqual(service.execute_push_calls, 0)
            app.push_screen(PushConfirmScreen(controller, preview))
            await wait_for_text(pilot, "#confirm-summary", "additions")
            await pilot.click("#btn-cancel")
            await pilot.pause()

    async def test_pull_worker_exception_and_token_mismatch(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PullScreen(controller))
            await wait_for_text(pilot, "#pull-summary", "custom diction")
            pull = app.screen
            assert isinstance(pull, PullScreen)
            await pilot.click("#btn-view-additions")
            await pilot.pause()
            app.pop_screen()
            with patch.object(controller, "prepare_pull", side_effect=RuntimeError("x")):
                err = PullScreen.load_pull_worker.__wrapped__(pull)
            self.assertEqual(err.plan_identifier, "error")
            self.assertIsNotNone(err.prepare_error)
            self.assertFalse(err.is_executable)
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
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Words to add")
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
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PushConfirmScreen(controller, typed))
            await wait_for_text(pilot, "#confirm-summary", "Type REMOVE")
            screen = app.screen
            assert isinstance(screen, PushConfirmScreen)
            screen.query_one("#confirm-input", Input).value = "push"
            run_btn = screen.query_one("#btn-run", Button)
            run_btn.disabled = False
            screen.on_button_pressed(Button.Pressed(run_btn))
            await pilot.pause()
            self.assertIsInstance(app.screen, PushConfirmScreen)

    async def test_push_confirm_non_typed_input_ignored(self):
        controller = TuiController(fake_service(), CliOptions())
        preview = sample_preview(removals=0)
        controller._active_push_preview = preview
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            screen = PushConfirmScreen(controller, preview)
            app.push_screen(screen)
            await wait_for_text(pilot, "#confirm-summary", "additions")
            screen.on_input_changed(Input.Changed(Input(), "x"))
            screen.action_cancel()
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

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
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(ReportScreen(controller, report))
            await wait_for_text(pilot, "#report-content", "stopped")
            screen = app.screen
            assert isinstance(screen, ReportScreen)
            # Non-dashboard top screen with a single-item stack hits the break.
            with patch.object(type(app), "screen_stack", property(lambda self: [screen])):
                screen._rebuild_preview()
                screen.action_back_dashboard()
            await pilot.pause()

    async def test_operation_screen_event_poll_and_worker_paths(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            screen = OperationScreen(
                controller,
                operation="push",
                push_preview=sample_preview(removals=0),
            )
            app.push_screen(screen)
            await pilot.pause()
            screen._apply_event(
                PresentedEvent(
                    operation=OperationKind.PUSH,
                    event_id=EventId.PUSH_ROLLBACK_STARTED,
                    message="Rolling back push transaction",
                    severity=EventSeverity.WARNING,
                    stage=EventStage.ROLLING_BACK,
                    target_id="chrome",
                )
            )
            screen._apply_event(
                PresentedEvent(
                    operation=OperationKind.PUSH,
                    event_id=EventId.PUSH_FINALIZING,
                    message="Finalizing transaction",
                    severity=EventSeverity.SUCCESS,
                    stage=EventStage.FINALIZING,
                    completed=1,
                    total=2,
                )
            )
            screen._finished = False
            screen._worker = SimpleNamespace(state=WorkerState.ERROR, result=None)
            screen._poll_operation()
            screen.on_execute_operation_worker_state_changed(
                SimpleNamespace(state=WorkerState.RUNNING, worker=None)
            )
            screen.on_execute_operation_worker_state_changed(
                SimpleNamespace(
                    state=WorkerState.ERROR,
                    worker=SimpleNamespace(result=None),
                )
            )
            self.assertTrue(any("Rolling back" in line for line in screen._stage_lines))
            self.assertTrue(screen._finished)

    async def test_operation_unknown_result_and_unmounted_guards(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            screen = OperationScreen(controller, operation="unknown")
            app.push_screen(screen)
            await wait_for_text(pilot, "#operation-stages-table", "no result")
            screen._worker = None
            screen._poll_operation()
            with patch.object(type(screen), "is_mounted", property(lambda self: False)):
                screen._flush_events()
                screen._finished = False
                screen._complete_with_result(None)
            self.assertFalse(screen._finished)

    async def test_pull_screen_mount_exception(self):
        service = fake_service()
        service.prepare_pull = lambda opts: (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore[method-assign]
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PullScreen(controller))
            summary = await wait_for_text(pilot, "#pull-summary", "unavailable")
            self.assertIn("unavailable", str(summary.render()).lower())

    async def test_push_confirm_removals_and_typed_guard(self):
        from spell_sync.tui.screens.removals_screen import RemovalsScreen

        controller = TuiController(fake_service(), CliOptions())
        typed = sample_preview(removals=2, plan_identifier="typed")
        controller._active_push_preview = typed
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PushConfirmScreen(controller, typed))
            await wait_for_text(pilot, "#confirm-summary", "Type REMOVE")
            await pilot.click("#btn-view-removals")
            await pilot.pause()
            self.assertIsInstance(app.screen, RemovalsScreen)
            app.pop_screen()
            screen = app.screen
            assert isinstance(screen, PushConfirmScreen)
            screen.query_one("#confirm-input", Input).value = "no"
            await pilot.click("#btn-run")
            await pilot.pause()
            self.assertTrue(screen.query_one("#btn-run").disabled)

    async def test_push_confirm_view_removals_aggregates_targets(self):
        from spell_sync.application.reports import TargetPreview
        from spell_sync.tui.screens.removals_screen import RemovalsScreen

        controller = TuiController(fake_service(), CliOptions())
        preview = sample_preview(
            removals=3,
            plan_identifier="multi-removals",
            targets=(
                TargetPreview(
                    name="chrome",
                    additions=0,
                    removals=0,
                    status="Unchanged",
                    removal_words=frozenset(),
                ),
                TargetPreview(
                    name="safari",
                    additions=1,
                    removals=2,
                    status="Review",
                    removal_words=frozenset({"alpha", "beta"}),
                ),
                TargetPreview(
                    name="edge",
                    additions=0,
                    removals=1,
                    status="Review",
                    removal_words=frozenset({"gamma"}),
                ),
            ),
        )
        controller._active_push_preview = preview
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PushConfirmScreen(controller, preview))
            await wait_for_text(pilot, "#confirm-summary", "Type REMOVE")
            await pilot.click("#btn-view-removals")
            await pilot.pause()
            self.assertIsInstance(app.screen, RemovalsScreen)
            removals = app.screen
            assert isinstance(removals, RemovalsScreen)
            self.assertEqual(removals._removal_words, frozenset({"alpha", "beta", "gamma"}))
            self.assertIn("safari", removals._title)

    async def test_finish_failed_records_report_for_review(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        reports: list[OperationReport] = []

        async with app.run_test(size=(100, 48)) as pilot:
            screen = OperationScreen(
                controller,
                operation="pull",
                pull_preview=sample_pull_preview(),
                on_complete=reports.append,
            )
            with patch.object(screen, "execute_operation_worker", return_value=None):
                app.push_screen(screen)
                await pilot.pause()
                screen._finish_failed("boom")
                self.assertIsNotNone(screen._report)
                assert screen._report is not None
                self.assertEqual(screen._report.outcome, OperationOutcome.FAILED)
                screen._dismiss_to_result()
                await pilot.pause()
            self.assertEqual(len(reports), 1)
            self.assertEqual(reports[0].outcome, OperationOutcome.FAILED)

    async def test_report_details_rebuild_and_recovery_navigation(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        stopped = OperationReport(
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
        recovery = OperationReport(
            operation="push",
            outcome=OperationOutcome.RECOVERY_REQUIRED,
            title="Push requires recovery",
            summary="incomplete",
            details=("meta",),
            warnings=("w",),
            recovery_required=True,
            conflict_target="chrome",
        )
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            app.push_screen(ReportScreen(controller, stopped))
            await wait_for_text(pilot, "#report-content", "stopped safely")
            await pilot.click("#btn-details")
            await pilot.pause()
            await pilot.click("#btn-rebuild")
            preview = await wait_for_text(pilot, "#preview-content", "Words to add")
            self.assertIn("Words to add", str(preview.render()))
            app.pop_screen()
            stopped_screen = ReportScreen(controller, stopped)
            app.push_screen(stopped_screen)
            await wait_for_text(pilot, "#report-content", "stopped safely")
            stopped_screen.on_button_pressed(
                type("E", (), {"button": type("B", (), {"id": "btn-dashboard"})()})()
            )
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)
            app.push_screen(ReportScreen(controller, recovery))
            await wait_for_text(pilot, "#report-content", "Push requires recovery")
            await pilot.click("#btn-details")
            content = await wait_for_text(pilot, "#report-content", "Finish interrupted update")
            self.assertIn("Finish interrupted update", str(content.render()))
            with patch.object(app, "exit") as exit_app:
                app.screen.on_button_pressed(
                    type("E", (), {"button": type("B", (), {"id": "btn-quit"})()})()
                )
                exit_app.assert_called_once_with(0)

    async def test_operation_unknown_dismiss_without_report(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            screen = OperationScreen(controller, operation="unknown")
            app.push_screen(screen)
            await wait_for_text(pilot, "#operation-stages-table", "no result")
            self.assertIsNotNone(screen._report)
            assert screen._report is not None
            self.assertEqual(screen._report.outcome, OperationOutcome.FAILED)
            screen._finished = True
            screen.on_button_pressed(
                type("E", (), {"button": type("B", (), {"id": "btn-close"})()})()
            )
            await pilot.pause()
            self.assertIsInstance(app.screen, ReportScreen)

    async def test_operation_safe_back_while_mutating(self):
        controller = TuiController(fake_service(), CliOptions())
        screen = OperationScreen(
            controller,
            operation="pull",
            pull_preview=sample_pull_preview(),
        )
        screen._mutating = True
        screen._finished = False
        with patch.object(screen, "notify") as notify:
            screen.action_safe_back()
            notify.assert_called_once()

    async def test_operation_safe_quit_while_mutating(self):
        controller = TuiController(fake_service(), CliOptions())
        screen = OperationScreen(
            controller,
            operation="pull",
            pull_preview=sample_pull_preview(),
        )
        screen._mutating = True
        screen._finished = False
        with patch.object(screen, "notify") as notify:
            screen.action_safe_quit()
            notify.assert_called_once()

    async def test_operation_dismiss_and_safe_quit_paths(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        report = OperationReport(
            operation="pull",
            outcome=OperationOutcome.COMPLETED,
            title="Collect my words completed",
            summary="ok",
        )
        async with app.run_test(size=(100, 48)) as pilot:
            screen = OperationScreen(
                controller,
                operation="pull",
                pull_preview=sample_pull_preview(),
            )
            with patch.object(screen, "execute_operation_worker", return_value=None):
                app.push_screen(screen)
                await pilot.pause()
                screen._finished = False
                screen._dismissed = False
                screen._dismiss_to_result()
                self.assertFalse(screen._dismissed)
                screen._finished = True
                screen._report = report
                screen.action_safe_back()
                await pilot.pause()
                self.assertIsInstance(app.screen, ReportScreen)
                # Race: UI flag cleared but controller mutation still held.
                screen._mutating = False
                screen._finished = False
                with patch.object(screen, "notify") as notify:
                    with patch.object(app, "exit") as exit_app:
                        screen.action_safe_quit()
                        notify.assert_called_once()
                        exit_app.assert_not_called()
                controller.end_mutation()
                with patch.object(app, "exit") as exit_app:
                    screen.action_safe_quit()
                    exit_app.assert_called_once_with(0)


if __name__ == "__main__":
    unittest.main()
