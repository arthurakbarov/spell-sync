"""Headless first-run setup wizard tests."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock

from spell_sync.application.reports import OperationOutcome
from spell_sync.cli_options import CliOptions
from spell_sync.project_setup.prepare import prepare_project_setup
from spell_sync.project_setup.state import ProjectSetupState, ProjectSetupStatus
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.dashboard import DashboardScreen
from spell_sync.tui.screens.setup_targets_screen import SetupTargetsScreen
from spell_sync.tui.screens.setup_welcome_screen import (
    SetupPreviewScreen,
    SetupWelcomeScreen,
    SetupWordlistScreen,
)
from tests.tui.fake_service import fake_service
from tests.tui.test_helpers import wait_for_text


class TestSetupFlow(unittest.IsolatedAsyncioTestCase):
    async def test_welcome_shown_when_project_missing(self):
        missing = ProjectSetupState(
            status=ProjectSetupStatus.MISSING_PROJECT,
            effective_wordlist=Path("/tmp/spell-words/wordlist.txt"),
            project_dir=Path("/tmp/spell-words"),
            config_path=None,
            can_start_wizard=True,
            detail="No Spell Sync project was found.",
        )
        controller = TuiController(fake_service(setup_state=missing), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await wait_for_text(pilot, "#welcome-content", "Welcome to Spell Sync")
            self.assertIsInstance(app.screen, SetupWelcomeScreen)

    async def test_quit_before_confirmation_creates_no_files(self):
        missing = ProjectSetupState(
            status=ProjectSetupStatus.MISSING_PROJECT,
            effective_wordlist=None,
            project_dir=None,
            config_path=None,
            can_start_wizard=True,
            detail=None,
        )
        service = fake_service(setup_state=missing)
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await wait_for_text(pilot, "#welcome-content", "Welcome")
            event = MagicMock()
            event.button.id = "btn-quit"
            app.screen.on_button_pressed(event)
            await pilot.pause()
        self.assertEqual(service.execute_setup_calls, 0)

    async def test_wordlist_back_preserves_session(self):
        missing = ProjectSetupState(
            status=ProjectSetupStatus.MISSING_PROJECT,
            effective_wordlist=None,
            project_dir=None,
            config_path=None,
            can_start_wizard=True,
            detail=None,
        )
        controller = TuiController(fake_service(setup_state=missing), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await wait_for_text(pilot, "#welcome-content", "Welcome")
            await pilot.click("#btn-setup")
            await pilot.pause()
            self.assertIsInstance(app.screen, SetupWordlistScreen)
            await pilot.click("#btn-back")
            await pilot.pause()
            self.assertIsInstance(app.screen, SetupWelcomeScreen)

    def test_setup_report_uses_setup_operation(self):
        from spell_sync.application.builders import build_setup_operation_report
        from spell_sync.project_setup.draft import SetupDraft
        from spell_sync.project_setup.execute import ProjectSetupExecution, ProjectSetupOutcome

        prepared = prepare_project_setup(
            SetupDraft(Path("/tmp/project/wordlist.txt"), (), create_wordlist=True),
        )
        execution = ProjectSetupExecution(
            prepared=prepared,
            outcome=ProjectSetupOutcome.COMPLETED,
            message="Project created.",
        )
        report = build_setup_operation_report(execution)
        self.assertEqual(report.operation, "setup")
        self.assertEqual(report.outcome, OperationOutcome.COMPLETED)

    async def test_invalid_config_does_not_launch_wizard(self):
        blocked = ProjectSetupState(
            status=ProjectSetupStatus.INVALID_CONFIG,
            effective_wordlist=Path("/tmp/wordlist.txt"),
            project_dir=Path("/tmp"),
            config_path=Path("/tmp/spell-sync.toml"),
            can_start_wizard=False,
            detail="Fix spell-sync.toml",
        )
        controller = TuiController(fake_service(setup_state=blocked), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Spell Sync")
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_wizard_navigation_to_preview(self):
        missing = ProjectSetupState(
            status=ProjectSetupStatus.MISSING_PROJECT,
            effective_wordlist=None,
            project_dir=None,
            config_path=None,
            can_start_wizard=True,
            detail=None,
        )
        controller = TuiController(fake_service(setup_state=missing), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            await wait_for_text(pilot, "#welcome-content", "Welcome")
            await pilot.click("#btn-setup")
            await pilot.pause()
            await pilot.click("#btn-continue")
            await pilot.pause()
            self.assertIsInstance(app.screen, SetupTargetsScreen)
            event = MagicMock()
            event.button.id = "btn-continue"
            app.screen.on_button_pressed(event)
            await pilot.pause()
            self.assertIsInstance(app.screen, SetupPreviewScreen)

    async def test_open_existing_project_continue(self):
        missing = ProjectSetupState(
            status=ProjectSetupStatus.MISSING_PROJECT,
            effective_wordlist=None,
            project_dir=None,
            config_path=None,
            can_start_wizard=True,
            detail=None,
        )
        service = fake_service(setup_state=missing)
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.click("#btn-open")
            await pilot.pause()
            app.screen.query_one("#wordlist-input").value = "/tmp/existing/wordlist.txt"
            await pilot.click("#btn-continue")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_wordlist_invalid_path_shows_error(self):
        missing = ProjectSetupState(
            status=ProjectSetupStatus.MISSING_PROJECT,
            effective_wordlist=None,
            project_dir=None,
            config_path=None,
            can_start_wizard=True,
            detail=None,
        )
        controller = TuiController(fake_service(setup_state=missing), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.click("#btn-setup")
            await pilot.pause()
            app.screen.query_one("#wordlist-input").value = "   "
            await pilot.click("#btn-continue")
            await pilot.pause()
            self.assertIsInstance(app.screen, SetupWordlistScreen)

    async def test_preview_back_returns_to_targets(self):
        missing = ProjectSetupState(
            status=ProjectSetupStatus.MISSING_PROJECT,
            effective_wordlist=None,
            project_dir=None,
            config_path=None,
            can_start_wizard=True,
            detail=None,
        )
        controller = TuiController(fake_service(setup_state=missing), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.click("#btn-setup")
            await pilot.pause()
            await pilot.click("#btn-continue")
            await pilot.pause()
            event = MagicMock()
            event.button.id = "btn-continue"
            app.screen.on_button_pressed(event)
            await pilot.pause()
            await pilot.click("#btn-back")
            await pilot.pause()
            self.assertIsInstance(app.screen, SetupTargetsScreen)


class TestSetupPreviewScreen(unittest.IsolatedAsyncioTestCase):
    async def test_preview_shows_external_dictionaries_unchanged(self):
        controller = TuiController(fake_service(), CliOptions())
        controller.set_setup_wordlist(Path("/tmp/new-project/wordlist.txt"))
        screen = SetupPreviewScreen(controller)
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(screen)
            await pilot.pause()
            content = app.screen.query_one("#preview-content").render()
            self.assertIn("No changes will be made", str(content))

    async def test_preview_create_runs_setup_execution(self):
        missing = ProjectSetupState(
            status=ProjectSetupStatus.MISSING_PROJECT,
            effective_wordlist=None,
            project_dir=None,
            config_path=None,
            can_start_wizard=True,
            detail=None,
        )
        service = fake_service(setup_state=missing)
        controller = TuiController(service, CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.click("#btn-setup")
            await pilot.pause()
            await pilot.click("#btn-continue")
            await pilot.pause()
            event = MagicMock()
            event.button.id = "btn-continue"
            app.screen.on_button_pressed(event)
            await pilot.pause()
            await pilot.click("#btn-create")
            await pilot.pause()
            await pilot.pause()
        self.assertEqual(service.execute_setup_calls, 1)


if __name__ == "__main__":
    unittest.main()
