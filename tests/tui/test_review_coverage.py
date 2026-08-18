"""Coverage tests for guided review workflow screens."""

import unittest
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from textual.worker import WorkerState

from spell_sync.application.product_concepts import push_preview_unavailable_message
from spell_sync.application.push_preview_copy import format_push_preview_summary
from spell_sync.application.reports import (
    OperationOutcome,
    OperationReport,
)
from spell_sync.application.requests import ProjectRef
from spell_sync.cli_options import CliOptions
from spell_sync.exit_codes import ExitCode
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.review_update_screen import (
    ReviewPullCompleteScreen,
    ReviewPullScreen,
    ReviewPushScreen,
    ReviewSessionReportScreen,
    _format_pull_preview,
)
from tests.tui.fake_service import fake_service, sample_preview, sample_pull_preview


class TestReviewCoverage(unittest.IsolatedAsyncioTestCase):
    def test_format_helpers(self):
        pull = sample_pull_preview(
            wordlist_error=ExitCode.PUSH_ABORT,
            prepare_error=ExitCode.PUSH_ABORT,
        )
        self.assertIn("unavailable", _format_pull_preview(pull))
        pull_ok = sample_pull_preview(warnings=("warn",))
        self.assertIn("warn", _format_pull_preview(pull_ok))
        self.assertIn("unavailable", push_preview_unavailable_message().lower())
        blocked = sample_preview(prepare_error=ExitCode.PUSH_ABORT)
        self.assertFalse(blocked.is_executable)
        normal = sample_preview(skipped=("offline",), warnings=("warn",))
        text = format_push_preview_summary(normal)
        self.assertIn("offline", text)
        self.assertIn("warn", text)

    def test_controller_review_helpers_without_session(self):
        controller = TuiController(fake_service(), CliOptions())
        controller.mark_review_pull_skipped()
        controller.mark_review_push_skipped()
        controller.record_review_pull_report(
            OperationReport("pull", OperationOutcome.COMPLETED, "t", "s")
        )
        controller.record_review_push_report(
            OperationReport("push", OperationOutcome.COMPLETED, "t", "s")
        )
        self.assertIsNone(controller.review_session())

    async def test_pull_screen_edge_paths(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            controller.begin_review_session()
            screen = ReviewPullScreen(controller)
            app.push_screen(screen)
            await pilot.pause()
            with patch.object(controller, "prepare_review_pull", side_effect=RuntimeError("boom")):
                screen.on_mount()
            self.assertIn("failed", str(screen.query_one("#review-pull-content").render()))
            screen._preview = None
            screen.action_run_pull()
            screen.action_skip_pull()
            screen.action_view_additions()
            screen._preview = sample_pull_preview(additions=0)
            screen.action_run_pull()
            controller.begin_mutation()
            screen.action_run_pull()
            controller.end_mutation()
            screen._starting = True
            screen.action_skip_pull()
            screen._starting = False
            screen._preview = sample_pull_preview()
            preview = screen._preview
            with patch.object(ReviewPullScreen, "is_mounted", new_callable=PropertyMock) as mounted:
                mounted.return_value = False
                screen._after_pull_confirm(preview, True)
            screen._after_pull_confirm(preview, False)
            with patch(
                "spell_sync.tui.screens.review_update_screen._review_should_end",
                return_value=False,
            ):
                pushed_fallback: list[str] = []

                def _capture_fallback(screen_obj):
                    pushed_fallback.append(type(screen_obj).__name__)

                with patch.object(screen.app, "push_screen", side_effect=_capture_fallback):
                    screen._on_pull_complete(
                        OperationReport("pull", OperationOutcome.FAILED, "Pull failed", "bad")
                    )
                self.assertEqual(pushed_fallback, ["ReviewSessionReportScreen"])
            pushed: list[str] = []

            def _capture(screen_obj):
                pushed.append(type(screen_obj).__name__)

            with patch.object(screen.app, "push_screen", side_effect=_capture):
                screen._on_pull_complete(
                    OperationReport("pull", OperationOutcome.FAILED, "Pull failed", "bad")
                )
                screen._on_pull_complete(
                    OperationReport(
                        "pull",
                        OperationOutcome.COMPLETED,
                        "Collect my words completed",
                        "ok",
                    )
                )
            self.assertIn("ReviewSessionReportScreen", pushed)
            self.assertIn("ReviewPullCompleteScreen", pushed)
            screen.action_back()
            await pilot.pause()

    async def test_pull_complete_and_push_worker_paths(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            controller.begin_review_session()
            screen = ReviewPushScreen(controller)
            app.push_screen(screen)
            await pilot.pause()
            screen._worker = SimpleNamespace(state=WorkerState.ERROR, result=None)
            screen._poll_push_worker()
            screen.on_load_push_preview_worker_state_changed(
                SimpleNamespace(state=WorkerState.RUNNING, worker=None)
            )
            screen.on_load_push_preview_worker_state_changed(
                SimpleNamespace(state=WorkerState.ERROR, worker=None)
            )
            with patch.object(controller, "prepare_review_push", side_effect=RuntimeError("boom")):
                result = screen.load_push_preview_worker.__wrapped__(screen)
            self.assertEqual(result.plan_identifier, "error")
            stale = screen._load_generation
            screen._active_token = stale - 1
            screen.on_load_push_preview_worker_state_changed(
                SimpleNamespace(
                    state=WorkerState.SUCCESS,
                    worker=SimpleNamespace(result=sample_preview()),
                )
            )
            screen._active_token = stale
            screen.on_load_push_preview_worker_state_changed(
                SimpleNamespace(
                    state=WorkerState.SUCCESS,
                    worker=SimpleNamespace(result=sample_preview()),
                )
            )
            screen.on_load_push_preview_worker_state_changed(
                SimpleNamespace(state=WorkerState.PENDING, worker=None)
            )
            screen._render_preview(sample_preview())
            screen._preview = None
            screen.action_view_removals()
            screen._preview = sample_preview(targets_to_update=0)
            screen.action_run_push()
            controller.begin_mutation()
            screen.action_finish_without_push()
            controller.end_mutation()
            screen._preview = sample_preview()
            screen._starting = True
            screen.action_finish_without_push()
            screen._starting = False

            preview = screen._preview
            with patch.object(ReviewPushScreen, "is_mounted", new_callable=PropertyMock) as mounted:
                mounted.return_value = False
                screen._after_push_confirm(preview, True)
            screen._after_push_confirm(preview, False)
            screen.on_button_pressed(SimpleNamespace(button=SimpleNamespace(id="btn-back")))
            complete = ReviewPullCompleteScreen(controller)
            app.push_screen(complete)
            await pilot.pause()
            with patch.object(app, "push_screen") as push_screen:
                complete.on_button_pressed(
                    SimpleNamespace(button=SimpleNamespace(id="btn-build-push"))
                )
                push_screen.assert_called_once()
            await pilot.pause()

    async def test_push_confirm_cancel_and_session_report_quit(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            controller.begin_review_session()
            push = ReviewPushScreen(controller)
            app.push_screen(push)
            await pilot.pause()
            push._preview = sample_preview()
            push._render_preview(push._preview)

            def _cancel(confirmed):
                assert confirmed is False

            from spell_sync.tui.screens.push_confirm_screen import PushConfirmScreen

            push.action_run_push()
            await pilot.pause()
            if isinstance(app.screen, PushConfirmScreen):
                app.screen.dismiss(False)
            await pilot.pause()

            report = ReviewSessionReportScreen(controller)
            app.push_screen(report)
            await pilot.pause()
            with patch.object(app, "exit") as exit_app:
                report.on_button_pressed(SimpleNamespace(button=SimpleNamespace(id="btn-quit")))
                exit_app.assert_called_once_with(0)
            await pilot.pause()

    async def test_prepare_review_pull_stores_prior_push_plan(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        controller.begin_review_session()
        session = controller.review_session()
        assert session is not None
        session.push_preview = sample_preview(plan_identifier="before-pull")
        preview = controller.prepare_review_pull()
        self.assertEqual(session.push_preview_plan_before_pull, "before-pull")
        self.assertIs(session.pull_preview, preview)


if __name__ == "__main__":
    unittest.main()
