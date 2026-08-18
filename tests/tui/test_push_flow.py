"""Headless Push confirmation and execution tests."""

import unittest
from dataclasses import replace

from spell_sync.application.product_concepts import (
    CONTINUE_TO_UPDATE_APPS_LABEL,
    UPDATE_CONFIRM_BUTTON,
)
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
from tests.tui.test_helpers import wait_for_operation_report, wait_for_text


class TestPushFlow(unittest.IsolatedAsyncioTestCase):
    async def test_zero_removal_confirmation(self):
        preview = sample_preview(
            removals=0,
            targets=(TargetPreview("chrome", 2, 0, "Ready"),),
        )
        service = fake_service(preview=preview)
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Words to add")
            self.assertEqual(
                str(app.screen.query_one("#btn-continue-push").label),
                CONTINUE_TO_UPDATE_APPS_LABEL,
            )
            await pilot.click("#btn-continue-push")
            summary = await wait_for_text(pilot, "#confirm-summary", "additions")
            self.assertEqual(str(app.screen.query_one("#btn-run").label), UPDATE_CONFIRM_BUTTON)
            self.assertIn("0 removals", str(summary.render()))
            self.assertNotIn("Type REMOVE", str(summary.render()))

    async def test_typed_confirmation_required(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Words to add")
            await pilot.click("#btn-continue-push")
            await wait_for_text(pilot, "#confirm-summary", "Type REMOVE")
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
            confirm_input.value = "REMOVE"
            screen.on_input_changed(Input.Changed(confirm_input, "REMOVE"))
            await pilot.pause()
            self.assertFalse(screen.query_one("#btn-run").disabled)

    async def test_execute_uses_same_prepared_object(self):
        prepared_preview = sample_preview(plan_identifier="fixed-plan")
        service = fake_service(preview=prepared_preview)
        # Keep plan id stable for this test
        service.load_push_preview = lambda opts: prepared_preview  # type: ignore[method-assign]
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Words to add")
            preview = app.screen._preview
            assert preview is not None
            await pilot.click("#btn-continue-push")
            await wait_for_text(pilot, "#confirm-summary", "Type REMOVE")
            from textual.widgets import Input

            confirm = app.screen
            assert isinstance(confirm, PushConfirmScreen)
            confirm_input = confirm.query_one("#confirm-input", Input)
            confirm_input.value = "REMOVE"
            confirm.on_input_changed(Input.Changed(confirm_input, "REMOVE"))
            await pilot.pause()
            await pilot.click("#btn-run")
            await wait_for_operation_report(pilot, "Update my apps completed")
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
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Words to add")
            await pilot.click("#btn-continue-push")
            await wait_for_text(pilot, "#confirm-summary", "additions")
            await pilot.click("#btn-run")
            report = await wait_for_operation_report(pilot, "Preview is stale")
            await pilot.click("#btn-details")
            await pilot.pause()
            self.assertIn("no conflicting file was overwritten", str(report.render()).lower())
            await pilot.click("#btn-rebuild")
            await wait_for_text(pilot, "#preview-content", "Words to add")

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
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Words to add")
            await pilot.click("#btn-continue-push")
            await wait_for_text(pilot, "#confirm-summary", "additions")
            await pilot.click("#btn-run")
            await wait_for_operation_report(pilot, "Rollback incomplete")

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
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Words to add")
            await pilot.click("#btn-continue-push")
            await wait_for_text(pilot, "#confirm-summary", "additions")
            await pilot.click("#btn-run")
            await wait_for_operation_report(pilot, "warnings")

    async def test_old_preview_invalidated_on_refresh(self):
        service = fake_service()
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Words to add")
            old = app.screen._preview
            assert old is not None
            old_id = old.plan_identifier
            await pilot.click("#btn-refresh-preview")
            await wait_for_text(pilot, "#preview-content", "Words to add")
            new = app.screen._preview
            assert new is not None
            self.assertNotEqual(old_id, new.plan_identifier)
            confirm = PushConfirmScreen(controller, old)
            app.push_screen(confirm)
            await wait_for_text(pilot, "#confirm-summary", "Type REMOVE")
            from textual.widgets import Input

            confirm_input = app.screen.query_one("#confirm-input", Input)
            confirm_input.value = "REMOVE"
            app.screen.on_input_changed(Input.Changed(confirm_input, "REMOVE"))
            await pilot.pause()
            await pilot.click("#btn-run")
            await pilot.pause()
            self.assertEqual(service.execute_push_calls, 0)

    async def test_continue_disabled_without_prepared(self):
        preview = replace(sample_preview(), prepared=None, prepare_error=ExitCode.PUSH_ABORT)
        controller = TuiController(fake_service(preview=preview), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "unavailable")
            btn = app.screen.query_one("#btn-continue-push")
            self.assertFalse(btn.display)
            self.assertEqual(app.screen.query_one("#btn-back").variant, "primary")

    async def test_zero_update_hides_continue_and_empty_viewers(self):
        preview = sample_preview(
            additions=0,
            removals=0,
            targets_to_update=0,
            unchanged=1,
            targets=(TargetPreview("chrome", 0, 0, "Unchanged"),),
        )
        controller = TuiController(fake_service(preview=preview), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Dictionaries to update")
            screen = app.screen
            self.assertFalse(screen.query_one("#btn-continue-push").display)
            self.assertFalse(screen.query_one("#btn-view-additions").display)
            self.assertFalse(screen.query_one("#btn-view-removals").display)
            self.assertEqual(screen.query_one("#btn-back").variant, "primary")


if __name__ == "__main__":
    unittest.main()
