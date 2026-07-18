"""Interactive setup target selection screen tests."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock

from spell_sync.cli_options import CliOptions
from spell_sync.project_setup.discovery import SetupTarget, SetupTargetDiscovery
from spell_sync.project_setup.selection import SetupSelection
from spell_sync.project_setup.state import ProjectSetupState, ProjectSetupStatus
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.setup_targets_screen import SetupTargetRowWidget, SetupTargetsScreen
from spell_sync.tui.screens.setup_welcome_screen import SetupPreviewScreen
from tests.tui.fake_service import fake_service


def _target(
    identifier: str,
    *,
    selectable: bool = True,
    enabled_by_default: bool = True,
    status: str = "ok",
    detail: str | None = None,
    detected: bool = True,
) -> SetupTarget:
    return SetupTarget(
        identifier=identifier,
        display_name=identifier.title(),
        path=Path(f"/tmp/{identifier}.txt") if detected else None,
        format_name="text",
        detected=detected,
        available=detectable if (detectable := detected and status == "ok") else False,
        readable=status in {"ok", "empty"},
        supported=True,
        enabled_by_default=enabled_by_default and selectable,
        selectable=selectable,
        word_count=3 if detected else None,
        status=status,
        detail=detail,
    )


def _discovery(*targets: SetupTarget) -> SetupTargetDiscovery:
    default_enabled = tuple(
        target.identifier for target in targets if target.enabled_by_default and target.selectable
    )
    return SetupTargetDiscovery(targets=targets, default_enabled=default_enabled)


def _button_event(button_id: str):
    class _Button:
        id = button_id

    class _Event:
        button = _Button()

    return _Event()


class TestSetupTargetsScreen(unittest.IsolatedAsyncioTestCase):
    def _controller_with_discovery(self, discovery: SetupTargetDiscovery) -> TuiController:
        service = fake_service(
            setup_state=ProjectSetupState(
                status=ProjectSetupStatus.MISSING_PROJECT,
                effective_wordlist=None,
                project_dir=None,
                config_path=None,
                can_start_wizard=False,
                detail=None,
            )
        )
        service.discover_setup_targets = MagicMock(return_value=discovery)
        controller = TuiController(service, CliOptions())
        controller.set_setup_wordlist(Path("/tmp/setup/wordlist.txt"))
        controller._setup_discovery = discovery
        controller._setup_selection = SetupSelection(
            frozenset(
                target.identifier for target in discovery.targets if target.enabled_by_default
            )
        )
        return controller

    async def test_default_selected_targets_rendered(self):
        discovery = _discovery(_target("chrome"), _target("firefox"))
        controller = self._controller_with_discovery(discovery)
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(SetupTargetsScreen(controller, "detail"))
            await pilot.pause()
            row = app.screen.query_one("#target-row-chrome", SetupTargetRowWidget)
            checkbox = row.query_one("#target-checkbox-chrome")
            self.assertTrue(checkbox.value)

    async def test_keyboard_toggle_updates_selection(self):
        discovery = _discovery(_target("chrome"), _target("firefox"))
        controller = self._controller_with_discovery(discovery)
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(SetupTargetsScreen(controller, "detail"))
            await pilot.pause()
            row = app.screen.query_one("#target-row-firefox", SetupTargetRowWidget)
            row.focus()
            app.screen.action_toggle_focused()
            await pilot.pause()
            self.assertIn("firefox", controller.setup_selected_targets)

    async def test_disabled_corrupt_target_cannot_toggle(self):
        discovery = _discovery(
            _target("chrome"),
            _target(
                "cursor",
                selectable=False,
                enabled_by_default=False,
                status="corrupt",
                detail="Corrupt dictionary",
            ),
        )
        controller = self._controller_with_discovery(discovery)
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(SetupTargetsScreen(controller, "detail"))
            await pilot.pause()
            row = app.screen.query_one("#target-row-cursor", SetupTargetRowWidget)
            row.focus()
            app.screen.action_toggle_focused()
            await pilot.pause()
            self.assertNotIn("cursor", controller.setup_selected_targets)

    async def test_back_preserves_selection(self):
        discovery = _discovery(_target("chrome"), _target("firefox"))
        controller = self._controller_with_discovery(discovery)
        controller._setup_selection = SetupSelection(frozenset({"firefox"}))
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(SetupTargetsScreen(controller, "detail"))
            await pilot.pause()
            event = _button_event("btn-continue")
            app.screen.on_button_pressed(event)
            await pilot.pause()
            self.assertIsInstance(app.screen, SetupPreviewScreen)
            await pilot.click("#btn-back")
            await pilot.pause()
            self.assertIsInstance(app.screen, SetupTargetsScreen)
            self.assertEqual(controller.setup_selected_targets, ("firefox",))

    async def test_continue_disabled_during_refresh(self):
        discovery = _discovery(_target("chrome"))
        controller = self._controller_with_discovery(discovery)
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(SetupTargetsScreen(controller, "detail"))
            await pilot.pause()
            app.screen._set_refreshing(True)
            await pilot.pause()
            self.assertTrue(
                app.screen.query_one(
                    "#btn-continue", __import__("textual.widgets").widgets.Button
                ).disabled
            )

    async def test_preview_uses_exact_selection(self):
        discovery = _discovery(
            _target("chrome"), _target("jetbrains", detected=False, selectable=False)
        )
        controller = self._controller_with_discovery(discovery)
        controller._setup_selection = SetupSelection(frozenset({"chrome"}))
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 32)) as pilot:
            app.push_screen(SetupPreviewScreen(controller))
            await pilot.pause()
            content = str(app.screen.query_one("#preview-content").render())
            self.assertIn("Chrome", content)
            self.assertIn("Not enabled:", content)
            self.assertIn("Jetbrains", content)


if __name__ == "__main__":
    unittest.main()
