"""Direct setup screen handler coverage."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from textual.widgets import Static

from spell_sync.cli_options import CliOptions
from spell_sync.project_setup.state import ProjectSetupState, ProjectSetupStatus
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
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
            event = MagicMock()
            event.button.id = "btn-back"
            app.screen.on_button_pressed(event)
            await pilot.pause()

    async def test_open_project_invalid_path(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupOpenProjectScreen(controller))
            await pilot.pause()
            app.screen.query_one("#wordlist-input").value = ""
            event = MagicMock()
            event.button.id = "btn-continue"
            app.screen.on_button_pressed(event)
            await pilot.pause()

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
            app.screen.query_one("#wordlist-input").value = ""
            event = MagicMock()
            event.button.id = "btn-continue"
            app.screen.on_button_pressed(event)
            await pilot.pause()

    async def test_preview_create_without_execute(self):
        controller = TuiController(fake_service(), CliOptions())
        controller.set_setup_wordlist(Path("/tmp/handler/wordlist.txt"))
        prepared = controller.prepare_setup_preview()
        service = controller._service
        service.setup_execution = None
        screen = SetupPreviewScreen(controller)
        screen._prepared = prepared
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(screen)
            await pilot.pause()
            if prepared.can_execute:
                event = MagicMock()
                event.button.id = "btn-create"
                app.screen.on_button_pressed(event)
                await pilot.pause()

    async def test_targets_back(self):
        controller = TuiController(fake_service(), CliOptions())
        controller.set_setup_wordlist(Path("/tmp/handler/targets-back/wordlist.txt"))
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupTargetsScreen(controller, "detail"))
            await pilot.pause()
            event = MagicMock()
            event.button.id = "btn-back"
            app.screen.on_button_pressed(event)
            await pilot.pause()

    async def test_targets_continue_to_preview(self):
        controller = TuiController(fake_service(), CliOptions())
        controller.set_setup_wordlist(Path("/tmp/handler/targets/wordlist.txt"))
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupTargetsScreen(controller, "detail"))
            await pilot.pause()
            event = MagicMock()
            event.button.id = "btn-continue"
            app.screen.on_button_pressed(event)
            await pilot.pause()
            self.assertIsInstance(app.screen, SetupPreviewScreen)

    async def test_preview_back(self):
        controller = TuiController(fake_service(), CliOptions())
        controller.set_setup_wordlist(Path("/tmp/handler/preview/wordlist.txt"))
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupPreviewScreen(controller))
            await pilot.pause()
            event = MagicMock()
            event.button.id = "btn-back"
            app.screen.on_button_pressed(event)
            await pilot.pause()

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


if __name__ == "__main__":
    unittest.main()
