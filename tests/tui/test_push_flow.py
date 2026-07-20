"""Headless Push confirmation and execution tests."""

from __future__ import annotations

import unittest
from dataclasses import replace

from spell_sync.application.reports import OperationOutcome, PushExecution, TargetPreview
from spell_sync.application.requests import ProjectRef
from spell_sync.cli_options import CliOptions
from spell_sync.exit_codes import ExitCode
from spell_sync.sync_models import PushResult
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.preview_screen import PreviewScreen
from spell_sync.tui.screens.push_confirm_screen import PushConfirmScreen
from tests.tui.fake_service import fake_service, sample_preview
from tests.tui.test_helpers import wait_for_text


class TestPushFlow(unittest.IsolatedAsyncioTestCase):
    async def test_zero_removal_confirmation(self):
        preview = sample_preview(
            removals=0,
            targets=(TargetPreview("chrome", 2, 0, "Ready"),),
        )
        service = fake_service(preview=preview)
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Plan id")
            await pilot.click("#btn-continue-push")
            summary = await wait_for_text(pilot, "#confirm-summary", "additions")
            self.assertIn("0 removals", str(summary.render()))
            self.assertNotIn("Type PUSH", str(summary.render()))

    async def test_typed_confirmation_required(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Plan id")
            await pilot.click("#btn-continue-push")
            await wait_for_text(pilot, "#confirm-summary", "Type PUSH")
            screen = app.screen
            assert isinstance(screen, PushConfirmScreen)
            run_btn = screen.query_one("#btn-run")
            self.assertTrue(run_btn.disabled)
            from textual.widgets import Input

            confirm_input = screen.query_one("#confirm-input", Input)
            confirm_input.value = "push"
            screen.on_input_changed(Input.Changed(confirm_input, "push"))
            await pilot.pause()
            self.assertTrue(run_btn.disabled)
            confirm_input.value = "PUSH"
            screen.on_input_changed(Input.Changed(confirm_input, "PUSH"))
            await pilot.pause()
            self.assertFalse(screen.query_one("#btn-run").disabled)

    async def test_execute_uses_same_prepared_object(self):
        prepared_preview = sample_preview(plan_identifier="fixed-plan")
        service = fake_service(preview=prepared_preview)
        # Keep plan id stable for this test
        service.load_push_preview = lambda opts: prepared_preview  # type: ignore[method-assign]
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Plan id")
            preview = app.screen._preview
            assert preview is not None
            await pilot.click("#btn-continue-push")
            await wait_for_text(pilot, "#confirm-summary", "Type PUSH")
            from textual.widgets import Input

            confirm = app.screen
            assert isinstance(confirm, PushConfirmScreen)
            confirm_input = confirm.query_one("#confirm-input", Input)
            confirm_input.value = "PUSH"
            confirm.on_input_changed(Input.Changed(confirm_input, "PUSH"))
            await pilot.pause()
            await pilot.click("#btn-run")
            await wait_for_text(pilot, "#report-content", "Push completed")
            self.assertIs(service.last_executed_prepared, preview.prepared)
            self.assertEqual(service.execute_push_calls, 1)

    async def test_conflict_report_and_rebuild(self):
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
        service.load_push_preview = lambda opts: preview  # type: ignore[method-assign]
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Plan id")
            await pilot.click("#btn-continue-push")
            await wait_for_text(pilot, "#confirm-summary", "additions")
            await pilot.click("#btn-run")
            report = await wait_for_text(pilot, "#report-content", "Preview is stale")
            self.assertIn("no conflicting file was overwritten", str(report.render()).lower())
            await pilot.click("#btn-rebuild")
            await wait_for_text(pilot, "#preview-content", "Plan id")

    async def test_recovery_required_report(self):
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
        service.load_push_preview = lambda opts: preview  # type: ignore[method-assign]
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Plan id")
            await pilot.click("#btn-continue-push")
            await wait_for_text(pilot, "#confirm-summary", "additions")
            await pilot.click("#btn-run")
            await wait_for_text(pilot, "#report-content", "requires recovery")

    async def test_partial_success(self):
        preview = sample_preview(removals=0, plan_identifier="partial-plan")
        service = fake_service(
            preview=preview,
            push_execution=PushExecution(
                prepared=preview.prepared,
                result=PushResult(
                    word_count=3,
                    written=("chrome",),
                    skipped=("jetbrains",),
                    skipped_reasons={"jetbrains": "Application is running"},
                ),
                outcome=OperationOutcome.COMPLETED_WITH_WARNINGS,
                message="partial",
                plan_identifier="partial-plan",
            ),
        )
        service.load_push_preview = lambda opts: preview  # type: ignore[method-assign]
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Plan id")
            await pilot.click("#btn-continue-push")
            await wait_for_text(pilot, "#confirm-summary", "additions")
            await pilot.click("#btn-run")
            await wait_for_text(pilot, "#report-content", "warnings")

    async def test_old_preview_invalidated_on_refresh(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Plan id:")
            old = app.screen._preview
            assert old is not None
            old_id = old.plan_identifier
            await pilot.click("#btn-refresh-preview")
            await wait_for_text(pilot, "#preview-content", "Plan id:")
            new = app.screen._preview
            assert new is not None
            self.assertNotEqual(old_id, new.plan_identifier)
            confirm = PushConfirmScreen(controller, old)
            app.push_screen(confirm)
            await wait_for_text(pilot, "#confirm-summary", "Type PUSH")
            from textual.widgets import Input

            confirm_input = app.screen.query_one("#confirm-input", Input)
            confirm_input.value = "PUSH"
            app.screen.on_input_changed(Input.Changed(confirm_input, "PUSH"))
            await pilot.pause()
            await pilot.click("#btn-run")
            await pilot.pause()
            self.assertEqual(service.execute_push_calls, 0)

    async def test_continue_disabled_without_prepared(self):
        preview = replace(sample_preview(), prepared=None, prepare_error=ExitCode.PUSH_ABORT)
        controller = TuiController(fake_service(preview=preview), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Plan blocked")
            btn = app.screen.query_one("#btn-continue-push")
            self.assertTrue(btn.disabled)


if __name__ == "__main__":
    unittest.main()
