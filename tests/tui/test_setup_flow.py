"""Headless first-run setup wizard tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from textual.widgets import Input, RadioButton, RadioSet, Static

from spell_sync.application.reports import OperationOutcome
from spell_sync.application.requests import ProjectRef
from spell_sync.cli_options import CliOptions
from spell_sync.project_setup.prepare import prepare_project_setup
from spell_sync.project_setup.state import ProjectSetupState, ProjectSetupStatus
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.dashboard import DashboardScreen
from spell_sync.tui.screens.doctor_screen import DoctorScreen
from spell_sync.tui.screens.logs_screen import TechnicalLogScreen
from spell_sync.tui.screens.operation_screen import OperationScreen
from spell_sync.tui.screens.report_screen import ReportScreen
from spell_sync.tui.screens.setup_targets_screen import SetupTargetsScreen
from spell_sync.tui.screens.setup_welcome_screen import (
    ChangeWordlistScreen,
    SetupOpenProjectScreen,
    SetupPreviewScreen,
    SetupWelcomeScreen,
    SetupWordlistScreen,
)
from tests.tui.fake_service import fake_service
from tests.tui.test_helpers import dismiss_operation_linger, wait_for_text


def _missing_project_state() -> ProjectSetupState:
    return ProjectSetupState(
        status=ProjectSetupStatus.MISSING_PROJECT,
        effective_wordlist=None,
        project_dir=None,
        config_path=None,
        can_start_wizard=True,
        detail=None,
    )


class TestSetupFlow(unittest.IsolatedAsyncioTestCase):
    def test_wordlist_presets_default_to_documents(self):
        controller = TuiController(fake_service(), CliOptions())
        default = controller.setup_wordlist_default()
        presets = controller.setup_wordlist_presets()
        self.assertEqual(default, presets[0][1])
        self.assertEqual(presets[0][0], "Documents")

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
        controller = TuiController(service, ProjectRef())
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
        controller = TuiController(service, ProjectRef())
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
        controller = TuiController(service, ProjectRef())
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


class TestSetupWordlistInteractions(unittest.IsolatedAsyncioTestCase):
    async def test_preset_selection_updates_input(self):
        controller = TuiController(fake_service(setup_state=_missing_project_state()), CliOptions())
        presets = controller.setup_wordlist_presets()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(SetupWordlistScreen(controller))
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, SetupWordlistScreen)
            radioset = screen.query_one("#wordlist-preset", RadioSet)
            home_radio = screen.query_one("#wordlist-preset-1", RadioButton)
            screen.on_radio_set_changed(RadioSet.Changed(radioset, home_radio))
            self.assertEqual(
                screen.query_one("#wordlist-input", Input).value,
                str(presets[1][1]),
            )

    async def test_custom_preset_focuses_input(self):
        controller = TuiController(fake_service(setup_state=_missing_project_state()), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(SetupWordlistScreen(controller))
            await pilot.pause()
            await pilot.click("#wordlist-preset-custom")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, SetupWordlistScreen)
            self.assertIs(screen.query_one("#wordlist-input", Input), app.focused)

    async def test_continue_with_default_path(self):
        controller = TuiController(fake_service(setup_state=_missing_project_state()), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(SetupWordlistScreen(controller))
            await pilot.pause()
            await pilot.click("#btn-continue")
            await pilot.pause()
            self.assertIsInstance(app.screen, SetupTargetsScreen)
            self.assertEqual(controller._setup_wordlist, controller.setup_wordlist_default())


class TestSetupOpenProjectScreen(unittest.IsolatedAsyncioTestCase):
    async def test_back_pops_screen(self):
        controller = TuiController(fake_service(setup_state=_missing_project_state()), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(SetupWelcomeScreen(controller))
            await pilot.pause()
            app.push_screen(SetupOpenProjectScreen(controller))
            await pilot.pause()
            await pilot.click("#btn-back")
            await pilot.pause()
            self.assertIsInstance(app.screen, SetupWelcomeScreen)

    async def test_invalid_path_shows_error(self):
        controller = TuiController(fake_service(setup_state=_missing_project_state()), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(SetupOpenProjectScreen(controller))
            await pilot.pause()
            app.screen.query_one("#wordlist-input", Input).value = "   "
            await pilot.click("#btn-continue")
            await pilot.pause()
            self.assertIsInstance(app.screen, SetupOpenProjectScreen)


class TestChangeWordlistScreen(unittest.IsolatedAsyncioTestCase):
    async def test_prefills_current_wordlist(self):
        existing = Path("/tmp/existing-project/wordlist.txt")
        controller = TuiController(fake_service(), ProjectRef(wordlist=existing))
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(ChangeWordlistScreen(controller))
            await pilot.pause()
            self.assertEqual(
                app.screen.query_one("#wordlist-input", Input).value,
                str(existing),
            )

    async def test_valid_path_updates_project_and_returns(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            controller = TuiController(
                fake_service(),
                ProjectRef(wordlist=Path("/tmp/old/wordlist.txt")),
            )
            app = SpellSyncApp(controller)
            async with app.run_test(size=(100, 32)) as pilot:
                app.push_screen(DashboardScreen(controller))
                await pilot.pause()
                app.push_screen(ChangeWordlistScreen(controller))
                await pilot.pause()
                app.screen.query_one("#wordlist-input", Input).value = str(wordlist)
                await pilot.click("#btn-continue")
                await pilot.pause()
                self.assertIsInstance(app.screen, DashboardScreen)
                self.assertEqual(controller.project_wordlist, wordlist.resolve())

    async def test_invalid_path_stays_on_screen(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(ChangeWordlistScreen(controller))
            await pilot.pause()
            app.screen.query_one("#wordlist-input", Input).value = "   "
            await pilot.click("#btn-continue")
            await pilot.pause()
            self.assertIsInstance(app.screen, ChangeWordlistScreen)

    async def test_back_returns_to_dashboard(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(DashboardScreen(controller))
            await pilot.pause()
            app.push_screen(ChangeWordlistScreen(controller))
            await pilot.pause()
            await pilot.click("#btn-back")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)


class TestDashboardChangeWordlist(unittest.IsolatedAsyncioTestCase):
    async def test_change_wordlist_button_opens_screen(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            screen = app.screen
            assert isinstance(screen, DashboardScreen)
            screen.on_button_pressed(
                SimpleNamespace(button=SimpleNamespace(id="btn-change-wordlist"))
            )
            await pilot.pause()
            self.assertIsInstance(app.screen, ChangeWordlistScreen)


class TestOperationLinger(unittest.IsolatedAsyncioTestCase):
    async def test_key_dismisses_to_report(self):
        missing = _missing_project_state()
        service = fake_service(setup_state=missing)
        controller = TuiController(service, ProjectRef())
        controller.set_setup_wordlist(Path("/tmp/linger-key/wordlist.txt"))
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            prepared = controller.prepare_setup_preview()
            screen = SetupPreviewScreen(controller)
            screen._prepared = prepared
            app.push_screen(screen)
            await pilot.pause()
            await pilot.click("#btn-create")
            for _ in range(40):
                await pilot.pause()
                if isinstance(app.screen, OperationScreen):
                    if not app.screen.query_one("#btn-close").disabled:
                        break
            self.assertIsInstance(app.screen, OperationScreen)
            await pilot.press("a")
            await pilot.pause()
            self.assertIsInstance(app.screen, ReportScreen)

    async def test_close_button_dismisses_to_report(self):
        missing = _missing_project_state()
        service = fake_service(setup_state=missing)
        controller = TuiController(service, ProjectRef())
        controller.set_setup_wordlist(Path("/tmp/linger-close/wordlist.txt"))
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            prepared = controller.prepare_setup_preview()
            screen = SetupPreviewScreen(controller)
            screen._prepared = prepared
            app.push_screen(screen)
            await pilot.pause()
            await pilot.click("#btn-create")
            await dismiss_operation_linger(pilot)
            self.assertIsInstance(app.screen, ReportScreen)


class TestDoctorTechnicalLog(unittest.IsolatedAsyncioTestCase):
    async def test_technical_log_button_opens_screen(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(DoctorScreen(controller))
            await wait_for_text(pilot, "#doctor-content", "Doctor")
            screen = app.screen
            assert isinstance(screen, DoctorScreen)
            screen.on_button_pressed(SimpleNamespace(button=SimpleNamespace(id="btn-tech-log")))
            await pilot.pause()
            self.assertIsInstance(app.screen, TechnicalLogScreen)


class TestSetupPreviewRendering(unittest.IsolatedAsyncioTestCase):
    async def test_preview_lists_enabled_and_not_enabled_targets(self):
        controller = TuiController(fake_service(setup_state=_missing_project_state()), CliOptions())
        controller.set_setup_wordlist(Path("/tmp/preview-targets/wordlist.txt"))
        discovery = controller.setup_target_discovery()
        first = discovery.targets[0].identifier
        controller.clear_setup_target_selection()
        controller.toggle_setup_target(first)
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            app.push_screen(SetupPreviewScreen(controller))
            await pilot.pause()
            content = str(app.screen.query_one("#preview-content", Static).render())
            self.assertIn("Enabled targets:", content)
            self.assertIn("Not enabled:", content)

    async def test_preview_shows_kept_wordlist_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            controller = TuiController(
                fake_service(setup_state=_missing_project_state()), CliOptions()
            )
            controller.set_setup_wordlist(wordlist)
            app = SpellSyncApp(controller)
            async with app.run_test(size=(100, 40)) as pilot:
                app.push_screen(SetupPreviewScreen(controller))
                await pilot.pause()
                content = str(app.screen.query_one("#preview-content", Static).render())
                self.assertIn("kept unchanged", content)


if __name__ == "__main__":
    unittest.main()
