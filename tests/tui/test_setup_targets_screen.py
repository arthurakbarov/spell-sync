"""Interactive setup target selection screen tests.

Method notes:
- Compact 80x24 visibility is required for list+action screens.
- Select available / Clear must go through the real button and assert checkboxes;
  controller-only calls miss Changed re-entry undoing the bulk update.
"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock

from spell_sync.application.requests import ProjectRef
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
        controller = TuiController(service, ProjectRef())
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
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupTargetsScreen(controller, "detail"))
            await pilot.pause()
            row = app.screen.query_one("#target-row-chrome", SetupTargetRowWidget)
            checkbox = row.query_one("#target-checkbox-chrome")
            self.assertTrue(checkbox.value)

    async def test_keyboard_toggle_updates_selection(self):
        discovery = _discovery(_target("chrome"), _target("firefox"))
        controller = self._controller_with_discovery(discovery)
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
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
                "not-a-config-target",
                selectable=False,
                enabled_by_default=False,
                status="corrupt",
                detail="Corrupt dictionary",
            ),
        )
        controller = self._controller_with_discovery(discovery)
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupTargetsScreen(controller, "detail"))
            await pilot.pause()
            row = app.screen.query_one("#target-row-not-a-config-target", SetupTargetRowWidget)
            row.focus()
            app.screen.action_toggle_focused()
            await pilot.pause()
            self.assertNotIn("not-a-config-target", controller.setup_selected_targets)

    async def test_back_preserves_selection(self):
        discovery = _discovery(_target("chrome"), _target("firefox"))
        controller = self._controller_with_discovery(discovery)
        controller._setup_selection = SetupSelection(frozenset({"firefox"}))
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
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

    async def test_preview_uses_exact_selection(self):
        discovery = _discovery(
            _target("chrome"),
            _target("sublime"),
            _target("jetbrains", detected=False, selectable=False, detail="Not found"),
        )
        controller = self._controller_with_discovery(discovery)
        controller._setup_selection = SetupSelection(frozenset({"chrome"}))
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupPreviewScreen(controller))
            await pilot.pause()
            content = str(app.screen.query_one("#preview-content").render())
            self.assertIn("Chrome", content)
            self.assertIn("Not enabled:", content)
            self.assertIn("Sublime", content)
            self.assertIn("Unavailable:", content)
            self.assertIn("Jetbrains", content)
            self.assertNotIn("Not enabled:\n  Jetbrains", content.replace("\r", ""))

    async def test_compact_terminal_keeps_target_rows_visible(self):
        discovery = _discovery(_target("chrome"), _target("firefox"), _target("editors"))
        controller = self._controller_with_discovery(discovery)
        long_detail = "\n\n".join(
            [
                "Resolved path:\n/Users/someone/code/my-words/wordlist.txt",
                "Project directory:\n/Users/someone/code/my-words",
                "Existing word list: 1745 words",
                "Existing config detected:\n/Users/someone/code/my-words/spell-sync.toml",
            ]
        )
        app = SpellSyncApp(controller)
        terminal = (80, 24)
        async with app.run_test(size=terminal) as pilot:
            app.push_screen(SetupTargetsScreen(controller, long_detail))
            await pilot.pause()
            await pilot.pause()
            body = app.screen.query_one("#screen-body")
            actions = app.screen.query_one("#targets-actions")
            container = app.screen.query_one("#targets-list")
            header = app.screen.query_one("#targets-header")
            # Single page scroll — no docked #screen-actions (regression: dock ate 80 by 24).
            self.assertEqual(len(app.screen.query("#screen-actions")), 0)
            self.assertGreaterEqual(body.region.height, 10)
            self.assertGreater(container.region.height, 0)
            header_text = str(header.render())
            self.assertIn("Applications", header_text)
            self.assertNotIn("/Users/someone", header_text)
            self.assertIn("my-words", header_text)
            # Equal-width stacked actions live in the same scroll as the list.
            continue_btn = app.screen.query_one("#btn-continue")
            select = app.screen.query_one("#btn-select-available")
            clear = app.screen.query_one("#btn-clear")
            back = app.screen.query_one("#btn-back")
            self.assertEqual(len(app.screen.query("#btn-refresh")), 0)
            for button in (continue_btn, select, clear, back):
                self.assertEqual(button.region.width, continue_btn.region.width)
            self.assertEqual(continue_btn.region.width, 36)
            # Back is below Clear in the same action stack (reachable via page scroll).
            self.assertGreater(back.region.y, clear.region.y)
            self.assertGreater(actions.region.y, container.region.y)
            rows = list(app.screen.query(SetupTargetRowWidget))
            self.assertGreaterEqual(len(rows), 3)
            body_bottom = body.region.y + body.region.height
            visible = [
                row
                for row in rows
                if row.region.height > 0
                and row.region.y >= body.region.y
                and row.region.y < body_bottom
            ]
            self.assertGreaterEqual(len(visible), 2)
            status = str(app.screen.query_one("#targets-status").render())
            self.assertIn("selected", status)
            self.assertNotIn("checklist scrolls", status)

    async def test_select_available_updates_status(self):
        discovery = _discovery(_target("chrome"), _target("firefox", enabled_by_default=False))
        controller = self._controller_with_discovery(discovery)
        self.assertEqual(set(controller.setup_selected_targets), {"chrome"})
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupTargetsScreen(controller, "detail"))
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, SetupTargetsScreen)
            button = screen.query_one("#btn-select-available")
            button.press()
            await pilot.pause()
            self.assertEqual(set(controller.setup_selected_targets), {"chrome", "firefox"})
            status = str(screen.query_one("#targets-status").render())
            self.assertRegex(status, r"2/2")
            firefox_box = screen.query_one("#target-checkbox-firefox")
            self.assertTrue(firefox_box.value)


if __name__ == "__main__":
    unittest.main()
