"""Setup screen handler behavior (navigation and validation feedback)."""

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from textual.widgets import Static

from spell_sync.application.requests import ProjectRef
from spell_sync.cli_options import CliOptions
from spell_sync.project_setup.state import ProjectSetupState, ProjectSetupStatus
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.dashboard import DashboardScreen
from spell_sync.tui.screens.setup_targets_screen import SetupTargetsScreen
from spell_sync.tui.screens.setup_welcome_screen import (
    SetupOpenProjectScreen,
    SetupPreviewScreen,
    SetupWordlistScreen,
)
from tests.tui.fake_service import fake_service


class TestSetupScreenHandlers(unittest.IsolatedAsyncioTestCase):
    async def test_open_project_back(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupOpenProjectScreen(controller))
            await pilot.pause()
            self.assertIsInstance(app.screen, SetupOpenProjectScreen)
            await pilot.click("#btn-back")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_open_project_invalid_path(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupOpenProjectScreen(controller))
            await pilot.pause()
            app.screen.query_one("#wordlist-input").value = ""
            await pilot.click("#btn-continue")
            await pilot.pause()
            # Invalid empty path notifies and stays on the open-project screen.
            self.assertIsInstance(app.screen, SetupOpenProjectScreen)

    async def test_wordlist_invalid_path(self):
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
            app.push_screen(SetupWordlistScreen(controller))
            await pilot.pause()
            await pilot.click("#wordlist-preset-custom")
            await pilot.pause()
            app.screen.query_one("#wordlist-input").value = ""
            await pilot.click("#btn-continue")
            await pilot.pause()
            self.assertIsInstance(app.screen, SetupWordlistScreen)

    async def test_preview_create_disabled_when_not_executable(self):
        controller = TuiController(fake_service(), CliOptions())
        controller.set_setup_wordlist(Path("/tmp/handler/wordlist.txt"))
        prepared = controller.prepare_setup_preview()
        blocked = replace(prepared, can_execute=False, conflicts=("blocked for test",))
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            with patch.object(controller, "prepare_setup_preview", return_value=blocked):
                app.push_screen(SetupPreviewScreen(controller))
                await pilot.pause()
            create = app.screen.query_one("#btn-create")
            self.assertTrue(create.disabled)
            content = str(app.screen.query_one("#preview-content").render())
            self.assertIn("Cannot create project", content)
            self.assertIn("blocked for test", content)
            self.assertIsInstance(app.screen, SetupPreviewScreen)

    async def test_targets_back(self):
        controller = TuiController(fake_service(), CliOptions())
        controller.set_setup_wordlist(Path("/tmp/handler/targets-back/wordlist.txt"))
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupTargetsScreen(controller, "detail"))
            await pilot.pause()
            await pilot.click("#btn-back")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_targets_continue_to_preview(self):
        controller = TuiController(fake_service(), CliOptions())
        controller.set_setup_wordlist(Path("/tmp/handler/targets/wordlist.txt"))
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupTargetsScreen(controller, "detail"))
            await pilot.pause()
            await pilot.click("#btn-continue")
            await pilot.pause()
            self.assertIsInstance(app.screen, SetupPreviewScreen)

    async def test_preview_back(self):
        controller = TuiController(fake_service(), CliOptions())
        controller.set_setup_wordlist(Path("/tmp/handler/preview/wordlist.txt"))
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupPreviewScreen(controller))
            await pilot.pause()
            await pilot.click("#btn-back")
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

    async def test_preview_shows_kept_wordlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            controller = TuiController(fake_service(), CliOptions())
            controller.set_setup_wordlist(wordlist)
            prepared = controller.prepare_setup_preview()
            app = SpellSyncApp(controller)
            async with app.run_test(size=(100, 48)) as pilot:
                screen = SetupPreviewScreen(controller)
                screen._prepared = prepared
                app.push_screen(screen)
                await pilot.pause()
                content = app.screen.query_one("#preview-content", Static).render()
                self.assertIn("kept unchanged", str(content))

    async def test_preview_existing_config_offers_open_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            (root / "spell-sync.toml").write_text(
                "[dictionaries]\neditors = true\n", encoding="utf-8"
            )
            controller = TuiController(fake_service(), CliOptions())
            controller.set_setup_wordlist(wordlist)
            app = SpellSyncApp(controller)
            async with app.run_test(size=(100, 48)) as pilot:
                app.push_screen(SetupPreviewScreen(controller))
                await pilot.pause()
                content = str(app.screen.query_one("#preview-content").render())
                self.assertIn("Cannot create project", content)
                self.assertIn("spell-sync.toml already exists", content)
                create = app.screen.query_one("#btn-create")
                open_btn = app.screen.query_one("#btn-open-existing")
                self.assertFalse(create.display)
                self.assertTrue(open_btn.display)
                app.screen.on_button_pressed(
                    type(
                        "E",
                        (),
                        {"button": type("B", (), {"id": "btn-open-existing"})()},
                    )()
                )
                await pilot.pause()
                self.assertIsInstance(app.screen, DashboardScreen)
                self.assertEqual(controller.project_wordlist, wordlist)

    async def test_open_existing_from_wizard_stack_reaches_dashboard(self):
        """Wizard-first apps have no Dashboard under Setup*; must not switch_screen."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            (root / "spell-sync.toml").write_text(
                "[dictionaries]\neditors = true\n", encoding="utf-8"
            )
            missing = ProjectSetupState(
                status=ProjectSetupStatus.MISSING_PROJECT,
                effective_wordlist=None,
                project_dir=None,
                config_path=None,
                can_start_wizard=True,
                detail=None,
            )
            controller = TuiController(fake_service(setup_state=missing), ProjectRef())
            controller.set_setup_wordlist(wordlist)
            app = SpellSyncApp(controller)
            async with app.run_test(size=(100, 48)) as pilot:
                await pilot.pause()
                self.assertTrue(
                    any(type(screen).__name__.startswith("Setup") for screen in app.screen_stack)
                )
                self.assertFalse(
                    any(isinstance(screen, DashboardScreen) for screen in app.screen_stack)
                )
                app.push_screen(SetupPreviewScreen(controller))
                await pilot.pause()
                open_btn = app.screen.query_one("#btn-open-existing")
                self.assertTrue(open_btn.display)
                app.screen.on_button_pressed(
                    type(
                        "E",
                        (),
                        {"button": type("B", (), {"id": "btn-open-existing"})()},
                    )()
                )
                await pilot.pause()
                self.assertIsInstance(app.screen, DashboardScreen)
                self.assertEqual(controller.project_wordlist, wordlist)


if __name__ == "__main__":
    unittest.main()
