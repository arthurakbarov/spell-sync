"""Headless Recovery flow tests."""

from __future__ import annotations

import unittest

from spell_sync.application.reports import RecoveryStatus
from spell_sync.application.requests import ProjectRef
from spell_sync.cli_options import CliOptions
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.recovery_confirm_screen import RecoveryConfirmScreen
from spell_sync.tui.screens.recovery_screen import RecoveryScreen
from tests.tui.fake_service import fake_service, sample_recovery_preview
from tests.tui.test_helpers import wait_for_text


class TestRecoveryFlow(unittest.IsolatedAsyncioTestCase):
    async def test_recovery_screen_absent(self):
        preview = sample_recovery_preview(
            status=RecoveryStatus.ABSENT,
            can_recover=False,
            detail="No unfinished transaction was found.",
        )
        controller = TuiController(
            fake_service(pending_recovery=True, recovery_preview=preview),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(RecoveryScreen(controller))
            await wait_for_text(pilot, "#recovery-content", "No unfinished transaction")

    async def test_typed_recover_confirmation(self):
        preview = sample_recovery_preview()
        service = fake_service(pending_recovery=True, recovery_preview=preview)
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(RecoveryScreen(controller))
            await wait_for_text(pilot, "#recovery-content", "Recoverable files")
            await pilot.click("#btn-recover")
            await wait_for_text(pilot, "#confirm-summary", "Type RECOVER")
            from textual.widgets import Input

            screen = app.screen
            assert isinstance(screen, RecoveryConfirmScreen)
            confirm_input = screen.query_one("#confirm-input", Input)
            confirm_input.value = "RECOVER"
            screen.on_input_changed(Input.Changed(confirm_input, "RECOVER"))
            await pilot.click("#btn-run")
            await wait_for_text(pilot, "#report-content", "Recovery completed")
            self.assertEqual(service.execute_recovery_calls, 1)

    async def test_dashboard_recovery_enabled(self):
        controller = TuiController(
            fake_service(pending_recovery=True),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await wait_for_text(pilot, "#blocking-banner", "Pending recovery")
            await pilot.click("#btn-recovery")
            await wait_for_text(pilot, "#recovery-content", "Recoverable files")

    async def test_recovery_screen_recoverable_notice(self):
        preview = sample_recovery_preview(status=RecoveryStatus.RECOVERABLE)
        controller = TuiController(
            fake_service(pending_recovery=True, recovery_preview=preview),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(RecoveryScreen(controller))
            content = await wait_for_text(pilot, "#recovery-content", "Pending recovery")
            self.assertIn("unfinished push journal", str(content.render()).lower())

    async def test_recovery_screen_in_progress_notice(self):
        preview = sample_recovery_preview(status=RecoveryStatus.RECOVERY_IN_PROGRESS)
        controller = TuiController(
            fake_service(pending_recovery=True, recovery_preview=preview),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(RecoveryScreen(controller))
            content = await wait_for_text(pilot, "#recovery-content", "Rollback incomplete")
            self.assertIn("Automatic rollback", str(content.render()))

    async def test_recovery_screen_corrupt_journal_notice(self):
        preview = sample_recovery_preview(
            status=RecoveryStatus.CORRUPT_JOURNAL,
            detail="unsupported schema",
            can_discard=True,
        )
        controller = TuiController(
            fake_service(pending_recovery=True, recovery_preview=preview),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(RecoveryScreen(controller))
            content = await wait_for_text(pilot, "#recovery-content", "Corrupt push journal")
            self.assertIn("unsupported schema", str(content.render()))


if __name__ == "__main__":
    unittest.main()
