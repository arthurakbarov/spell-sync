"""Headless first-run setup wizard tests."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from textual.widgets import Button, Input, RadioButton, RadioSet, Static

from spell_sync.application.reports import OperationOutcome
from spell_sync.application.requests import ProjectRef
from spell_sync.cli_options import CliOptions
from spell_sync.project_setup.discovery import SetupTarget, SetupTargetDiscovery
from spell_sync.project_setup.prepare import prepare_project_setup
from spell_sync.project_setup.selection import SetupSelection
from spell_sync.project_setup.state import ProjectSetupState, ProjectSetupStatus
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.path_picker import WordlistPathPicker
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
    SetupStorageMoreOptionsScreen,
    SetupStorageStrategyScreen,
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


async def _advance_to_wordlist(pilot, app: SpellSyncApp) -> None:
    """Welcome -> wordlist (local storage is the silent default)."""
    await wait_for_text(pilot, "#welcome-content", "Welcome")
    await pilot.click("#btn-setup")
    await pilot.pause()
    assert isinstance(app.screen, SetupWordlistScreen)


async def _advance_to_targets(pilot, app: SpellSyncApp) -> None:
    """Welcome -> wordlist -> targets."""
    await _advance_to_wordlist(pilot, app)
    await pilot.click("#btn-continue")
    await pilot.pause()
    assert isinstance(app.screen, SetupTargetsScreen)


class TestSetupFlow(unittest.IsolatedAsyncioTestCase):
    def test_wordlist_presets_default_to_documents(self):
        controller = TuiController(fake_service(), CliOptions())
        default = controller.setup_wordlist_default()
        presets = controller.setup_wordlist_presets()
        self.assertEqual(default, presets[0][1])
        self.assertEqual(presets[0][0], "Documents")

    def test_set_setup_storage_strategy_rejects_unknown(self):
        from spell_sync.application.product_concepts import STORAGE_STRATEGY_LOCAL

        controller = TuiController(fake_service(), CliOptions())
        with self.assertRaisesRegex(ValueError, "unknown storage strategy"):
            controller.set_setup_storage_strategy("not-a-strategy")
        controller.set_setup_storage_strategy(STORAGE_STRATEGY_LOCAL)
        self.assertEqual(controller.setup_storage_strategy(), STORAGE_STRATEGY_LOCAL)

    async def test_storage_strategy_ignores_unknown_radio(self):
        from spell_sync.application.product_concepts import STORAGE_STRATEGY_LOCAL
        from spell_sync.tui.screens.setup_welcome_screen import SetupStorageMoreOptionsScreen

        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupStorageMoreOptionsScreen(controller))
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, SetupStorageMoreOptionsScreen)
            pressed = MagicMock()
            pressed.id = "storage-unknown"
            screen.on_radio_set_changed(MagicMock(pressed=pressed))
            self.assertEqual(screen._selected, STORAGE_STRATEGY_LOCAL)

    async def test_welcome_shown_when_project_missing(self):
        missing = ProjectSetupState(
            status=ProjectSetupStatus.MISSING_PROJECT,
            effective_wordlist=Path("/tmp/my-words/wordlist.txt"),
            project_dir=Path("/tmp/my-words"),
            config_path=None,
            can_start_wizard=True,
            detail="No Spell Sync project was found.",
        )
        controller = TuiController(fake_service(setup_state=missing), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
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
        async with app.run_test(size=(100, 48)) as pilot:
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
        async with app.run_test(size=(100, 48)) as pilot:
            await _advance_to_wordlist(pilot, app)
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
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Your personal word list")
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
        async with app.run_test(size=(100, 48)) as pilot:
            await _advance_to_targets(pilot, app)
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
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / "existing" / "wordlist.txt"
            existing.parent.mkdir(parents=True)
            existing.write_text("alpha\n", encoding="utf-8")
            service = fake_service(setup_state=missing)
            controller = TuiController(service, ProjectRef())
            app = SpellSyncApp(controller)
            async with app.run_test(size=(100, 48)) as pilot:
                await pilot.click("#btn-open")
                await pilot.pause()
                app.screen.query_one("#wordlist-input").value = str(existing)
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
        async with app.run_test(size=(100, 48)) as pilot:
            await _advance_to_wordlist(pilot, app)
            # Preset Continue ignores the hidden picker; exercise Custom empty path.
            await pilot.click("#wordlist-preset-custom")
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
        async with app.run_test(size=(100, 48)) as pilot:
            await _advance_to_targets(pilot, app)
            event = MagicMock()
            event.button.id = "btn-continue"
            app.screen.on_button_pressed(event)
            await pilot.pause()
            self.assertIsInstance(app.screen, SetupPreviewScreen)
            await pilot.click("#btn-back")
            await pilot.pause()
            self.assertIsInstance(app.screen, SetupTargetsScreen)


class TestSetupPreviewScreen(unittest.IsolatedAsyncioTestCase):
    async def test_preview_shows_external_dictionaries_unchanged(self):
        controller = TuiController(fake_service(), CliOptions())
        controller.set_setup_wordlist(Path("/tmp/new-project/wordlist.txt"))
        screen = SetupPreviewScreen(controller)
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
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
        async with app.run_test(size=(100, 48)) as pilot:
            await _advance_to_targets(pilot, app)
            event = MagicMock()
            event.button.id = "btn-continue"
            app.screen.on_button_pressed(event)
            await pilot.pause()
            self.assertIsInstance(app.screen, SetupPreviewScreen)
            await pilot.click("#btn-create")
            await pilot.pause()
            await pilot.pause()
            self.assertEqual(service.execute_setup_calls, 1)

    async def test_preview_action_back_handler(self):
        controller = TuiController(
            fake_service(setup_state=_missing_project_state()),
            CliOptions(),
        )
        controller.set_setup_wordlist(Path("/tmp/preview-back/wordlist.txt"))
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupPreviewScreen(controller))
            await pilot.pause()
            app.screen.action_back()
            await pilot.pause()


class TestSetupWordlistInteractions(unittest.IsolatedAsyncioTestCase):
    async def test_preset_selection_updates_input(self):
        controller = TuiController(fake_service(setup_state=_missing_project_state()), CliOptions())
        presets = controller.setup_wordlist_presets()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
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
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupWordlistScreen(controller))
            await pilot.pause()
            await pilot.click("#wordlist-preset-custom")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, SetupWordlistScreen)
            self.assertIs(screen.query_one("#wordlist-input", Input), app.focused)
            # Custom must not keep the Documents preset in the input.
            self.assertEqual(screen.query_one("#wordlist-input", Input).value, "~/")

    async def test_custom_continue_uses_typed_path_not_documents_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            custom = Path(tmp) / "my-words" / "wordlist.txt"
            custom.parent.mkdir(parents=True)
            custom.write_text("alpha\n", encoding="utf-8")
            controller = TuiController(
                fake_service(setup_state=_missing_project_state()), CliOptions()
            )
            app = SpellSyncApp(controller)
            async with app.run_test(size=(100, 48)) as pilot:
                app.push_screen(SetupWordlistScreen(controller))
                await pilot.pause()
                await pilot.click("#wordlist-preset-custom")
                await pilot.pause()
                screen = app.screen
                assert isinstance(screen, SetupWordlistScreen)
                screen.query_one("#wordlist-input", Input).value = str(custom)
                await pilot.click("#btn-continue")
                await pilot.pause()
                self.assertIsInstance(app.screen, SetupTargetsScreen)
                assert controller._setup_wordlist is not None
                self.assertEqual(controller._setup_wordlist.resolve(), custom.resolve())
                self.assertNotEqual(
                    controller._setup_wordlist.resolve(),
                    controller.setup_wordlist_default().resolve(),
                )

    async def test_custom_hides_use_selected_folder_and_promotes_continue(self):
        controller = TuiController(fake_service(setup_state=_missing_project_state()), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupWordlistScreen(controller))
            await pilot.pause()
            recommended = app.screen.query_one("#btn-recommended", Button)
            continue_btn = app.screen.query_one("#btn-continue", Button)
            self.assertTrue(recommended.display)
            self.assertEqual(recommended.variant, "primary")
            await pilot.click("#wordlist-preset-custom")
            await pilot.pause()
            self.assertFalse(recommended.display)
            self.assertEqual(continue_btn.variant, "primary")
            await pilot.click("#wordlist-preset-0")
            await pilot.pause()
            self.assertTrue(recommended.display)
            self.assertEqual(recommended.variant, "primary")
            self.assertEqual(continue_btn.variant, "default")

    async def test_recommended_while_custom_uses_typed_path_not_documents(self):
        """Primary used to mean Documents even with Custom path typed in the field."""
        with tempfile.TemporaryDirectory() as tmp:
            custom = Path(tmp) / "my-words" / "wordlist.txt"
            custom.parent.mkdir(parents=True)
            custom.write_text("alpha\n", encoding="utf-8")
            controller = TuiController(
                fake_service(setup_state=_missing_project_state()), CliOptions()
            )
            app = SpellSyncApp(controller)
            async with app.run_test(size=(100, 48)) as pilot:
                app.push_screen(SetupWordlistScreen(controller))
                await pilot.pause()
                await pilot.click("#wordlist-preset-custom")
                await pilot.pause()
                screen = app.screen
                assert isinstance(screen, SetupWordlistScreen)
                screen.query_one("#wordlist-input", Input).value = str(custom)
                # Force the old primary path even though the button is hidden.
                screen.on_button_pressed(
                    SimpleNamespace(button=SimpleNamespace(id="btn-recommended"))
                )
                await pilot.pause()
                self.assertIsInstance(app.screen, SetupTargetsScreen)
                assert controller._setup_wordlist is not None
                self.assertEqual(controller._setup_wordlist.resolve(), custom.resolve())
                self.assertNotEqual(
                    controller._setup_wordlist.resolve(),
                    controller.setup_wordlist_default().resolve(),
                )

    async def test_continue_with_default_path(self):
        controller = TuiController(fake_service(setup_state=_missing_project_state()), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
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
        async with app.run_test(size=(100, 48)) as pilot:
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
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupOpenProjectScreen(controller))
            await pilot.pause()
            app.screen.query_one("#wordlist-input", Input).value = "   "
            await pilot.click("#btn-continue")
            await pilot.pause()
            self.assertIsInstance(app.screen, SetupOpenProjectScreen)

    async def test_path_input_has_suggester_and_actions(self):
        home = Path.home()
        (home / "Documents").mkdir(exist_ok=True)
        controller = TuiController(fake_service(setup_state=_missing_project_state()), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(80, 28)) as pilot:
            app.push_screen(SetupOpenProjectScreen(controller))
            await pilot.pause()
            picker = app.screen.query_one(WordlistPathPicker)
            picker.refresh_completions()
            await pilot.pause()
            self.assertTrue(app.screen.query("#setup-actions"))
            self.assertTrue(app.screen.query("#path-complete-list"))
            self.assertIs(picker.query_one("#wordlist-input", Input), app.focused)
            # Empty field should list home matches.
            self.assertGreater(picker.query_one("#path-complete-list").option_count, 0)

    async def test_open_continue_uses_typed_path_not_home_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            custom = Path(tmp) / "guest-words" / "wordlist.txt"
            custom.parent.mkdir(parents=True)
            custom.write_text("alpha\n", encoding="utf-8")
            controller = TuiController(
                fake_service(setup_state=_missing_project_state()), CliOptions()
            )
            app = SpellSyncApp(controller)
            async with app.run_test(size=(100, 48)) as pilot:
                app.push_screen(SetupWelcomeScreen(controller))
                await pilot.pause()
                app.push_screen(SetupOpenProjectScreen(controller))
                await pilot.pause()
                # No recent yet → picker visible; type an absolute path.
                app.screen.query_one("#wordlist-input", Input).value = str(custom)
                await pilot.click("#btn-continue")
                await pilot.pause()
                self.assertIsInstance(app.screen, DashboardScreen)
                assert controller.project_wordlist is not None
                self.assertEqual(controller.project_wordlist.resolve(), custom.resolve())
                self.assertNotEqual(
                    controller.project_wordlist.resolve(),
                    Path.home().resolve(),
                )

    async def test_open_continue_uses_recent_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            recent_path = Path(tmp) / "recent" / "wordlist.txt"
            recent_path.parent.mkdir(parents=True)
            recent_path.write_text("beta\n", encoding="utf-8")
            from spell_sync.project_memory import remember_wordlist

            remember_wordlist(recent_path)
            controller = TuiController(
                fake_service(setup_state=_missing_project_state()), CliOptions()
            )
            app = SpellSyncApp(controller)
            async with app.run_test(size=(100, 48)) as pilot:
                app.push_screen(SetupWelcomeScreen(controller))
                await pilot.pause()
                app.push_screen(SetupOpenProjectScreen(controller))
                await pilot.pause()
                self.assertTrue(app.screen.query("#recent-wordlist"))
                self.assertFalse(app.screen.query_one(WordlistPathPicker).display)
                await pilot.click("#btn-continue")
                await pilot.pause()
                self.assertIsInstance(app.screen, DashboardScreen)
                assert controller.project_wordlist is not None
                self.assertEqual(controller.project_wordlist.resolve(), recent_path.resolve())

    async def test_open_continue_commits_list_highlight_without_enter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            custom = root / "wordlist.txt"
            custom.write_text("alpha\n", encoding="utf-8")
            controller = TuiController(
                fake_service(setup_state=_missing_project_state()), CliOptions()
            )
            app = SpellSyncApp(controller)
            async with app.run_test(size=(100, 48)) as pilot:
                app.push_screen(SetupWelcomeScreen(controller))
                await pilot.pause()
                app.push_screen(SetupOpenProjectScreen(controller))
                await pilot.pause()
                picker = app.screen.query_one(WordlistPathPicker)
                picker.path_value = str(root) + "/"
                await pilot.pause()
                option_list = picker.query_one("#path-complete-list")
                self.assertGreater(option_list.option_count, 0)
                # Leave Input as directory prefix; highlight wordlist.txt if present.
                completions = picker._completions
                try:
                    index = next(
                        i for i, value in enumerate(completions) if value.endswith("wordlist.txt")
                    )
                except StopIteration:
                    self.fail(f"expected wordlist.txt in completions, got {completions!r}")
                option_list.highlighted = index
                await pilot.click("#btn-continue")
                await pilot.pause()
                self.assertIsInstance(app.screen, DashboardScreen)
                assert controller.project_wordlist is not None
                self.assertEqual(controller.project_wordlist.resolve(), custom.resolve())


class TestSetupWelcomeLayout(unittest.IsolatedAsyncioTestCase):
    async def test_welcome_layout_uses_bottom_actions(self):
        controller = TuiController(fake_service(setup_state=_missing_project_state()), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            self.assertIsInstance(app.screen, SetupWelcomeScreen)
            self.assertTrue(app.screen.query("#setup-actions"))
            self.assertTrue(app.screen.query(".setup-body"))


class TestChangeWordlistScreen(unittest.IsolatedAsyncioTestCase):
    async def test_prefills_current_wordlist(self):
        existing = Path("/tmp/existing-project/wordlist.txt")
        controller = TuiController(fake_service(), ProjectRef(wordlist=existing))
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(ChangeWordlistScreen(controller))
            await pilot.pause()
            self.assertEqual(
                app.screen.query_one("#wordlist-input", Input).value,
                str(existing),
            )
            self.assertTrue(app.screen.query(WordlistPathPicker))

    async def test_path_label_not_flush_under_recent_radios(self):
        with tempfile.TemporaryDirectory() as tmp:
            recent = Path(tmp) / "wordlist.txt"
            recent.write_text("alpha\n", encoding="utf-8")
            controller = TuiController(fake_service(), ProjectRef(wordlist=recent))
            controller.recent_wordlists = lambda: (recent,)  # type: ignore[method-assign]
            app = SpellSyncApp(controller)
            async with app.run_test(size=(100, 48)) as pilot:
                app.push_screen(ChangeWordlistScreen(controller))
                await pilot.pause()
                await pilot.click("#recent-other")
                await pilot.pause()
                radios = app.screen.query_one("#recent-wordlist")
                label = app.screen.query_one("#change-path-label")
                self.assertTrue(label.display)
                gap = label.region.y - (radios.region.y + radios.region.height)
                self.assertGreaterEqual(gap, 1)


class TestSetupOpenProjectSpacing(unittest.IsolatedAsyncioTestCase):
    async def test_path_label_not_flush_under_recent_radios(self):
        with tempfile.TemporaryDirectory() as tmp:
            recent = Path(tmp) / "wordlist.txt"
            recent.write_text("alpha\n", encoding="utf-8")
            controller = TuiController(fake_service(), CliOptions())
            controller.recent_wordlists = lambda: (recent,)  # type: ignore[method-assign]
            app = SpellSyncApp(controller)
            async with app.run_test(size=(100, 48)) as pilot:
                app.push_screen(SetupOpenProjectScreen(controller))
                await pilot.pause()
                await pilot.click("#recent-other")
                await pilot.pause()
                radios = app.screen.query_one("#recent-wordlist")
                label = app.screen.query_one("#open-path-label")
                self.assertTrue(label.display)
                gap = label.region.y - (radios.region.y + radios.region.height)
                self.assertGreaterEqual(gap, 1)

    async def test_valid_path_updates_project_and_returns(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            old = Path("/tmp/old/wordlist.txt")
            controller = TuiController(
                fake_service(),
                ProjectRef(wordlist=old),
            )
            app = SpellSyncApp(controller)
            async with app.run_test(size=(100, 48)) as pilot:
                app.push_screen(DashboardScreen(controller))
                await pilot.pause()
                app.push_screen(ChangeWordlistScreen(controller))
                await pilot.pause()
                app.screen.query_one("#wordlist-input", Input).value = str(wordlist)
                await pilot.click("#btn-continue")
                await pilot.pause()
                self.assertIsInstance(app.screen, DashboardScreen)
                self.assertEqual(controller.project_wordlist, wordlist.resolve())
                self.assertNotEqual(controller.project_wordlist, old.resolve())

    async def test_change_continue_without_edits_keeps_prefill(self):
        with tempfile.TemporaryDirectory() as tmp:
            current = Path(tmp) / "wordlist.txt"
            current.write_text("keep\n", encoding="utf-8")
            controller = TuiController(fake_service(), ProjectRef(wordlist=current))
            app = SpellSyncApp(controller)
            async with app.run_test(size=(100, 48)) as pilot:
                app.push_screen(DashboardScreen(controller))
                await pilot.pause()
                app.push_screen(ChangeWordlistScreen(controller))
                await pilot.pause()
                await pilot.click("#btn-continue")
                await pilot.pause()
                self.assertIsInstance(app.screen, DashboardScreen)
                assert controller.project_wordlist is not None
                self.assertEqual(controller.project_wordlist.resolve(), current.resolve())

    async def test_change_continue_commits_list_highlight_from_directory_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            new_wordlist = root / "wordlist.txt"
            new_wordlist.write_text("beta\n", encoding="utf-8")
            old = Path("/tmp/stale-prefill/wordlist.txt")
            controller = TuiController(fake_service(), ProjectRef(wordlist=old))
            app = SpellSyncApp(controller)
            async with app.run_test(size=(100, 48)) as pilot:
                app.push_screen(DashboardScreen(controller))
                await pilot.pause()
                app.push_screen(ChangeWordlistScreen(controller))
                await pilot.pause()
                picker = app.screen.query_one(WordlistPathPicker)
                self.assertEqual(picker.path_value, str(old))
                picker.path_value = str(root) + "/"
                await pilot.pause()
                option_list = picker.query_one("#path-complete-list")
                completions = picker._completions
                try:
                    index = next(
                        i for i, value in enumerate(completions) if value.endswith("wordlist.txt")
                    )
                except StopIteration:
                    self.fail(f"expected wordlist.txt in completions, got {completions!r}")
                option_list.highlighted = index
                await pilot.click("#btn-continue")
                await pilot.pause()
                self.assertIsInstance(app.screen, DashboardScreen)
                assert controller.project_wordlist is not None
                self.assertEqual(controller.project_wordlist.resolve(), new_wordlist.resolve())
                self.assertNotEqual(controller.project_wordlist.resolve(), old.resolve())

    async def test_invalid_path_stays_on_screen(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(ChangeWordlistScreen(controller))
            await pilot.pause()
            app.screen.query_one("#wordlist-input", Input).value = "   "
            await pilot.click("#btn-continue")
            await pilot.pause()
            self.assertIsInstance(app.screen, ChangeWordlistScreen)

    async def test_back_returns_to_dashboard(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
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
            content = str(app.screen.query_one("#change-wordlist-content").render())
            label = str(app.screen.query_one("#change-path-label").render())
            # Intro must not repeat the field label owned by #change-path-label.
            self.assertNotIn("Path to wordlist.txt:", content)
            self.assertEqual(label.strip(), "Path to wordlist.txt:")


class TestOperationLinger(unittest.IsolatedAsyncioTestCase):
    async def test_key_dismisses_to_report(self):
        missing = _missing_project_state()
        service = fake_service(setup_state=missing)
        controller = TuiController(service, ProjectRef())
        controller.set_setup_wordlist(Path("/tmp/linger-key/wordlist.txt"))
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
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
        async with app.run_test(size=(100, 48)) as pilot:
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
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(DoctorScreen(controller))
            await wait_for_text(pilot, "#doctor-summary", "Doctor")
            screen = app.screen
            assert isinstance(screen, DoctorScreen)
            screen.on_button_pressed(SimpleNamespace(button=SimpleNamespace(id="btn-tech-log")))
            await pilot.pause()
            self.assertIsInstance(app.screen, TechnicalLogScreen)


class TestSetupWelcomeCoverage(unittest.IsolatedAsyncioTestCase):
    async def test_welcome_quit_with_none_button_id(self):
        controller = TuiController(fake_service(setup_state=_missing_project_state()), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupWelcomeScreen(controller))
            await pilot.pause()
            event = MagicMock()
            event.button.id = None
            app.screen.on_button_pressed(event)
            await pilot.pause()
        self.assertFalse(app.is_running)

    async def test_storage_more_options_continue_and_back(self):
        controller = TuiController(fake_service(setup_state=_missing_project_state()), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupStorageStrategyScreen(controller))
            await pilot.pause()
            await pilot.click("#btn-more")
            await pilot.pause()
            assert isinstance(app.screen, SetupStorageMoreOptionsScreen)
            await pilot.click("#btn-continue")
            await pilot.pause()
            self.assertIsInstance(app.screen, SetupWordlistScreen)
            app.push_screen(SetupStorageMoreOptionsScreen(controller))
            await pilot.pause()
            app.screen.action_back()
            await pilot.pause()

    async def test_wordlist_recommended_without_presets(self):
        controller = TuiController(fake_service(setup_state=_missing_project_state()), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupWordlistScreen(controller))
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, SetupWordlistScreen)
            screen._presets = []
            screen.on_button_pressed(SimpleNamespace(button=SimpleNamespace(id="btn-recommended")))
            await pilot.pause()
            self.assertIsInstance(app.screen, SetupWordlistScreen)

    async def test_change_wordlist_refreshes_dashboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            controller = TuiController(fake_service(), ProjectRef(wordlist=Path("/tmp/old.txt")))
            app = SpellSyncApp(controller)
            async with app.run_test(size=(100, 48)) as pilot:
                dashboard = DashboardScreen(controller)
                app.push_screen(dashboard)
                await pilot.pause()
                app.push_screen(ChangeWordlistScreen(controller))
                await pilot.pause()
                screen = app.screen
                assert isinstance(screen, ChangeWordlistScreen)
                screen.query_one("#wordlist-input", Input).value = str(wordlist)
                screen.on_button_pressed(SimpleNamespace(button=SimpleNamespace(id="btn-continue")))
                await pilot.pause()
                self.assertIsInstance(app.screen, DashboardScreen)
                self.assertEqual(controller.project_wordlist, wordlist.resolve())


class TestSetupPreviewRendering(unittest.IsolatedAsyncioTestCase):
    async def test_preview_lists_enabled_and_not_enabled_targets(self):
        def _row(
            identifier: str,
            *,
            selectable: bool = True,
            status: str = "ok",
            detail: str | None = None,
        ) -> SetupTarget:
            return SetupTarget(
                identifier=identifier,
                display_name=identifier.title(),
                path=Path(f"/tmp/{identifier}.txt"),
                format_name="text",
                detected=True,
                available=selectable,
                readable=selectable,
                supported=True,
                enabled_by_default=selectable,
                selectable=selectable,
                word_count=1 if selectable else None,
                status=status,
                detail=detail,
            )

        discovery = SetupTargetDiscovery(
            targets=(
                _row("chrome"),
                _row("sublime"),
                _row("jetbrains", selectable=False, status="missing", detail="Not found"),
            ),
            default_enabled=("chrome",),
        )
        service = fake_service(setup_state=_missing_project_state())
        service.discover_setup_targets = MagicMock(return_value=discovery)
        controller = TuiController(service, CliOptions())
        controller.set_setup_wordlist(Path("/tmp/preview-targets/wordlist.txt"))
        controller._setup_discovery = discovery
        controller._setup_selection = SetupSelection(frozenset({"chrome"}))
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupPreviewScreen(controller))
            await pilot.pause()
            content = str(app.screen.query_one("#preview-content", Static).render())
            self.assertIn("Enabled apps:", content)
            self.assertIn("Chrome", content)
            self.assertIn("Not enabled:", content)
            self.assertIn("Sublime", content)
            self.assertIn("Unavailable:", content)
            self.assertIn("Jetbrains", content)

    async def test_preview_shows_kept_wordlist_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            controller = TuiController(
                fake_service(setup_state=_missing_project_state()), CliOptions()
            )
            controller.set_setup_wordlist(wordlist)
            app = SpellSyncApp(controller)
            async with app.run_test(size=(100, 48)) as pilot:
                app.push_screen(SetupPreviewScreen(controller))
                await pilot.pause()
                content = str(app.screen.query_one("#preview-content", Static).render())
                self.assertIn("kept unchanged", content)


if __name__ == "__main__":
    unittest.main()
