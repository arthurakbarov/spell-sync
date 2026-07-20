"""Headless guided Review and update workflow tests."""

from __future__ import annotations

import unittest

from spell_sync.application.reports import (
    OperationOutcome,
    PullExecution,
    PushExecution,
    TargetPreview,
)
from spell_sync.application.requests import ProjectRef
from spell_sync.cli_options import CliOptions
from spell_sync.exit_codes import ExitCode
from spell_sync.sync_models import PushResult
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.push_confirm_screen import PushConfirmScreen
from spell_sync.tui.screens.review_update_screen import (
    ReviewPullScreen,
    ReviewPushScreen,
    ReviewStartScreen,
)
from tests.tui.fake_service import fake_service, sample_preview, sample_pull_preview
from tests.tui.test_helpers import wait_for_text


class TestReviewWorkflow(unittest.IsolatedAsyncioTestCase):
    async def _open_review_pull(self, pilot, controller):
        await wait_for_text(pilot, "#dashboard-summary", "Ready")
        await pilot.click("#btn-review-update")
        await pilot.pause()
        await pilot.click("#btn-start")
        await wait_for_text(pilot, "#review-pull-content", "Pull review")

    async def _open_review_push(self, pilot, controller):
        await self._open_review_pull(pilot, controller)
        await pilot.click("#btn-skip")
        await wait_for_text(pilot, "#review-push-content", "Plan id:")

    async def test_review_start_screen(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.click("#btn-review-update")
            body = await wait_for_text(
                pilot,
                "#review-body",
                "Nothing changes without confirmation",
            )
            self.assertIn("review application custom dictionaries", str(body.render()))
            self.assertIsInstance(app.screen, ReviewStartScreen)
            self.assertIsNone(controller.review_session())

    async def test_pull_additions_flow(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await self._open_review_pull(pilot, controller)
            content = app.screen.query_one("#review-pull-content")
            rendered = str(content.render())
            self.assertIn("17 words were found in application custom dictionaries", rendered)
            self.assertIn("Sources ready: 2", rendered)
            await pilot.click("#btn-pull")
            await wait_for_text(pilot, "#confirm-summary", "Add 17 words")
            await pilot.click("#btn-run")
            await wait_for_text(pilot, "#review-pull-complete", "Pull completed")
            self.assertEqual(service.execute_pull_calls, 1)
            await pilot.click("#btn-build-push")
            await wait_for_text(pilot, "#review-push-content", "Total additions")

    async def test_pull_no_changes_message(self):
        preview = sample_pull_preview(additions=0, addition_words=frozenset())
        controller = TuiController(fake_service(pull_preview=preview), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await self._open_review_pull(pilot, controller)
            content = await wait_for_text(
                pilot,
                "#review-pull-content",
                "enabled custom dictionaries",
            )
            rendered = str(content.render())
            self.assertIn("All readable words from enabled custom dictionaries", rendered)
            await pilot.click("#btn-skip")
            await wait_for_text(pilot, "#review-push-content", "Plan id:")

    async def test_skip_pull_builds_fresh_push_preview(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await self._open_review_pull(pilot, controller)
            await wait_for_text(pilot, "#review-pull-content", "custom diction")
            before = service.preview_counter
            await pilot.click("#btn-skip")
            await wait_for_text(pilot, "#review-push-content", "Plan id:")
            self.assertGreater(service.preview_counter, before)
            session = controller.review_session()
            assert session is not None
            self.assertTrue(session.pull_skipped)

    async def test_fresh_push_preview_after_pull_execution(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await self._open_review_pull(pilot, controller)
            await wait_for_text(pilot, "#review-pull-content", "custom diction")
            session = controller.review_session()
            assert session is not None
            pre_pull_plan = session.push_preview_plan_before_pull
            await pilot.click("#btn-pull")
            await wait_for_text(pilot, "#confirm-summary", "Add 17 words")
            preview_before_push = service.preview_counter
            await pilot.click("#btn-run")
            await wait_for_text(pilot, "#review-pull-complete", "Build Push preview")
            await pilot.click("#btn-build-push")
            await wait_for_text(pilot, "#review-push-content", "Plan id:")
            self.assertGreater(service.preview_counter, preview_before_push)
            session = controller.review_session()
            assert session is not None
            assert session.push_preview is not None
            if pre_pull_plan is not None:
                self.assertNotEqual(session.push_preview.plan_identifier, pre_pull_plan)

    async def test_pull_write_failure_ends_session(self):
        preview = sample_pull_preview()
        service = fake_service(
            pull_execution=PullExecution(
                preview=preview,
                result=ExitCode.PUSH_ABORT,
                outcome=OperationOutcome.FAILED,
                message="write failed",
            )
        )
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await self._open_review_pull(pilot, controller)
            await wait_for_text(pilot, "#review-pull-content", "custom diction")
            await pilot.click("#btn-pull")
            await wait_for_text(pilot, "#confirm-summary", "Add 17 words")
            await pilot.click("#btn-run")
            report = await wait_for_text(pilot, "#review-session-report", "Pull: Failed")
            self.assertIn("Review complete", str(report.render()))

    async def test_push_no_changes_finish(self):
        preview = sample_preview(
            removals=0,
            additions=0,
            targets=(TargetPreview("chrome", 0, 0, "Unchanged"),),
            targets_to_update=0,
            unchanged=1,
        )
        service = fake_service(preview=preview)
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await self._open_review_pull(pilot, controller)
            await pilot.click("#btn-skip")
            await wait_for_text(pilot, "#review-push-content", "Targets to update: 0")
            await pilot.click("#btn-finish")
            report = await wait_for_text(pilot, "#review-session-report", "Push: Skipped")
            self.assertIn("Pull: Skipped", str(report.render()))

    async def test_skip_push_session_report(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await self._open_review_pull(pilot, controller)
            await pilot.click("#btn-skip")
            await wait_for_text(pilot, "#review-push-content", "Plan id:")
            await pilot.click("#btn-finish")
            report = await wait_for_text(pilot, "#review-session-report", "Push: Skipped")
            self.assertIn("No recovery is required", str(report.render()))

    async def test_push_with_typed_confirmation(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await self._open_review_pull(pilot, controller)
            await pilot.click("#btn-skip")
            await wait_for_text(pilot, "#review-push-content", "Total removals")
            await pilot.click("#btn-push")
            await wait_for_text(pilot, "#confirm-summary", "Type PUSH")
            from textual.widgets import Input

            screen = app.screen
            assert isinstance(screen, PushConfirmScreen)
            confirm_input = screen.query_one("#confirm-input", Input)
            confirm_input.value = "PUSH"
            screen.on_input_changed(Input.Changed(confirm_input, "PUSH"))
            await pilot.click("#btn-run")
            report = await wait_for_text(pilot, "#review-session-report", "Push: Completed")
            self.assertEqual(service.execute_push_calls, 1)
            self.assertIn("Pull: Skipped", str(report.render()))

    async def test_push_conflict_ends_session(self):
        preview = sample_preview(removals=0, plan_identifier="conflict-plan")
        service = fake_service(
            preview=preview,
            push_execution=PushExecution(
                prepared=preview.prepared,
                result=ExitCode.PUSH_ABORT,
                outcome=OperationOutcome.STOPPED_SAFELY,
                message="conflict",
                conflict_target="chrome",
                plan_identifier="conflict-plan",
            ),
        )
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await self._open_review_pull(pilot, controller)
            await pilot.click("#btn-skip")
            await wait_for_text(pilot, "#review-push-content", "Plan id")
            await pilot.click("#btn-push")
            await wait_for_text(pilot, "#confirm-summary", "additions")
            await pilot.click("#btn-run")
            report = await wait_for_text(pilot, "#review-session-report", "Push: Stopped safely")
            self.assertIn("Pull: Skipped", str(report.render()))

    async def test_push_recovery_required_ends_session(self):
        preview = sample_preview(removals=0, plan_identifier="recover-plan")
        service = fake_service(
            preview=preview,
            push_execution=PushExecution(
                prepared=preview.prepared,
                result=ExitCode.PUSH_ABORT,
                outcome=OperationOutcome.RECOVERY_REQUIRED,
                message="rollback incomplete",
                recovery_required=True,
                plan_identifier="recover-plan",
            ),
        )
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await self._open_review_pull(pilot, controller)
            await pilot.click("#btn-skip")
            await wait_for_text(pilot, "#review-push-content", "Plan id")
            await pilot.click("#btn-push")
            await wait_for_text(pilot, "#confirm-summary", "additions")
            await pilot.click("#btn-run")
            report = await wait_for_text(
                pilot,
                "#review-session-report",
                "Recovery is required",
            )
            self.assertIn("Push: Recovery required", str(report.render()))

    async def test_session_cleared_after_finish(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await self._open_review_pull(pilot, controller)
            await pilot.click("#btn-skip")
            await wait_for_text(pilot, "#review-push-content", "Plan id:")
            await pilot.click("#btn-finish")
            await wait_for_text(pilot, "#review-session-report", "Review complete")
            await pilot.click("#btn-dashboard")
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            self.assertIsNone(controller.review_session())

    async def test_back_from_start_clears_session(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.click("#btn-review-update")
            await pilot.pause()
            controller.begin_review_session()
            await pilot.click("#btn-back")
            await pilot.pause()
            self.assertIsNone(controller.review_session())

    async def test_back_from_pull_clears_session(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await self._open_review_pull(pilot, controller)
            await wait_for_text(pilot, "#review-pull-content", "custom diction")
            await pilot.click("#btn-back")
            await pilot.pause()
            self.assertIsNone(controller.review_session())

    async def test_view_additions(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await self._open_review_pull(pilot, controller)
            await wait_for_text(pilot, "#review-pull-content", "custom diction")
            await pilot.click("#btn-additions")
            await pilot.pause()
            from spell_sync.tui.screens.removals_screen import RemovalsScreen

            self.assertIsInstance(app.screen, RemovalsScreen)

    async def test_double_pull_guard(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            screen = ReviewPullScreen(controller)
            controller.begin_review_session()
            app.push_screen(screen)
            await pilot.pause()
            await wait_for_text(pilot, "#review-pull-content", "custom diction")
            screen._starting = True
            screen.action_run_pull()
            self.assertEqual(service.execute_pull_calls, 0)

    async def test_history_only_for_real_operations(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await self._open_review_pull(pilot, controller)
            await pilot.click("#btn-skip")
            await wait_for_text(pilot, "#review-push-content", "Plan id:")
            await pilot.click("#btn-finish")
            await wait_for_text(pilot, "#review-session-report", "Review complete")
            self.assertEqual(service.execute_pull_calls, 0)
            self.assertEqual(service.execute_push_calls, 0)

    async def test_full_pull_and_push_session_report(self):
        preview = sample_preview(removals=0, plan_identifier="push-plan")
        service = fake_service(
            preview=preview,
            push_execution=PushExecution(
                prepared=preview.prepared,
                result=PushResult(word_count=3, written=("chrome",)),
                outcome=OperationOutcome.COMPLETED,
                message="done",
                plan_identifier="push-plan",
            ),
        )
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await self._open_review_pull(pilot, controller)
            await wait_for_text(pilot, "#review-pull-content", "custom diction")
            await pilot.click("#btn-pull")
            await wait_for_text(pilot, "#confirm-summary", "Add 17 words")
            await pilot.click("#btn-run")
            await wait_for_text(pilot, "#review-pull-complete", "Build Push preview")
            await pilot.click("#btn-build-push")
            await wait_for_text(pilot, "#review-push-content", "Plan id")
            await pilot.click("#btn-push")
            await wait_for_text(pilot, "#confirm-summary", "additions")
            await pilot.click("#btn-run")
            report = await wait_for_text(pilot, "#review-session-report", "Pull: Completed")
            text = str(report.render())
            self.assertIn("Push: Completed", text)
            self.assertEqual(service.execute_pull_calls, 1)
            self.assertEqual(service.execute_push_calls, 1)

    async def test_view_removals_on_push_preview(self):
        words = frozenset({"alpha", "beta"})
        preview = sample_preview(
            targets=(
                TargetPreview(
                    name="chrome",
                    additions=0,
                    removals=2,
                    status="Review",
                    removal_words=words,
                ),
            ),
            removals=2,
        )
        controller = TuiController(fake_service(preview=preview), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            controller.begin_review_session()
            app.push_screen(ReviewPushScreen(controller))
            await pilot.pause()
            await wait_for_text(pilot, "#review-push-content", "Total removals")
            await pilot.click("#btn-view-removals")
            await pilot.pause()
            from spell_sync.tui.screens.removals_screen import RemovalsScreen

            self.assertIsInstance(app.screen, RemovalsScreen)

    async def test_push_back_navigation(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await self._open_review_pull(pilot, controller)
            await pilot.click("#btn-skip")
            await wait_for_text(pilot, "#review-push-content", "Plan id:")
            await pilot.click("#btn-back")
            await pilot.pause()
            self.assertIsInstance(app.screen, ReviewPullScreen)

    async def test_session_report_view_history(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await self._open_review_pull(pilot, controller)
            await pilot.click("#btn-skip")
            await wait_for_text(pilot, "#review-push-content", "Plan id:")
            await pilot.click("#btn-finish")
            await wait_for_text(pilot, "#review-session-report", "Review complete")
            await pilot.click("#btn-history")
            await pilot.pause()
            from spell_sync.tui.screens.logs_screen import LogsScreen

            self.assertIsInstance(app.screen, LogsScreen)

    async def test_stale_pull_preview_blocked(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await self._open_review_pull(pilot, controller)
            await wait_for_text(pilot, "#review-pull-content", "custom diction")
            preview = app.screen._preview
            assert preview is not None
            controller.invalidate_pull_preview()
            from spell_sync.tui.screens.pull_confirm_screen import PullConfirmScreen

            app.push_screen(PullConfirmScreen(controller, preview))
            await wait_for_text(pilot, "#confirm-summary", "Add 17 words")
            await pilot.click("#btn-run")
            await pilot.pause()
            self.assertEqual(service.execute_pull_calls, 0)
            self.assertIsInstance(app.screen, ReviewPullScreen)

    async def test_save_session_report_success(self):
        from pathlib import Path
        from unittest.mock import MagicMock

        from spell_sync.tui.screens.review_update_screen import ReviewSessionReportScreen

        controller = TuiController(fake_service(), CliOptions())
        controller.begin_review_session()
        session = controller.review_session()
        assert session is not None
        session.pull_skipped = True
        session.push_skipped = True
        controller.export_review_session_report = MagicMock(  # type: ignore[method-assign]
            return_value=Path("/tmp/session-reports/review-report-test.json")
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await app.push_screen(ReviewSessionReportScreen(controller))
            await pilot.click("#btn-save-report")
            await wait_for_text(pilot, "#session-report-export-status", "Report saved")
            controller.export_review_session_report.assert_called_once()

    async def test_save_session_report_reuses_saved_path(self):
        from spell_sync.tui.screens.review_update_screen import ReviewSessionReportScreen

        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            screen = ReviewSessionReportScreen(controller)
            screen._saved_report_path = "/tmp/already-saved.json"
            await app.push_screen(screen)
            await pilot.click("#btn-save-report")
            await wait_for_text(pilot, "#session-report-export-status", "Report already saved")

    async def test_save_session_report_ignores_repeated_click(self):
        import time
        from pathlib import Path
        from unittest.mock import MagicMock

        from spell_sync.tui.screens.review_update_screen import ReviewSessionReportScreen

        controller = TuiController(fake_service(), CliOptions())
        controller.begin_review_session()
        session = controller.review_session()
        assert session is not None
        session.pull_skipped = True
        session.push_skipped = True

        def slow_export(**kwargs: object) -> Path:
            time.sleep(0.3)
            return Path("/tmp/session-reports/review-report-test.json")

        controller.export_review_session_report = MagicMock(side_effect=slow_export)  # type: ignore[method-assign]
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await app.push_screen(ReviewSessionReportScreen(controller))
            await pilot.click("#btn-save-report")
            await pilot.click("#btn-save-report")
            await wait_for_text(pilot, "#session-report-export-status", "Report saved")
            self.assertEqual(controller.export_review_session_report.call_count, 1)

    async def test_save_session_report_ignores_stale_result(self):
        import asyncio
        from pathlib import Path
        from unittest.mock import MagicMock

        from spell_sync.tui.screens.review_update_screen import ReviewSessionReportScreen

        controller = TuiController(fake_service(), CliOptions())
        controller.begin_review_session()
        session = controller.review_session()
        assert session is not None
        session.pull_skipped = True
        session.push_skipped = True
        completed = asyncio.Event()

        def slow_export(**kwargs: object) -> Path:
            completed.wait(timeout=1)
            return Path("/tmp/session-reports/review-report-test.json")

        controller.export_review_session_report = MagicMock(side_effect=slow_export)  # type: ignore[method-assign]
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await app.push_screen(ReviewSessionReportScreen(controller))
            await pilot.click("#btn-save-report")
            await pilot.click("#btn-dashboard")
            completed.set()
            await pilot.pause(0.1)
            from spell_sync.tui.screens.dashboard import DashboardScreen

            self.assertIsInstance(app.screen, DashboardScreen)


if __name__ == "__main__":
    unittest.main()
