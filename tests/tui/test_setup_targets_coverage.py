"""Additional setup targets screen coverage."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

from textual.worker import Worker, WorkerState

from spell_sync.application.requests import ProjectRef
from spell_sync.cli_options import CliOptions
from spell_sync.project_setup.discovery import SetupTarget, SetupTargetDiscovery
from spell_sync.project_setup.selection import SetupSelection
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.setup_targets_screen import SetupTargetRowWidget, SetupTargetsScreen
from spell_sync.tui.screens.setup_welcome_screen import SetupPreviewScreen
from tests.tui.fake_service import fake_service


def _target(
    identifier: str,
    *,
    selectable: bool = True,
    detected: bool = True,
    status: str = "ok",
    detail: str | None = None,
) -> SetupTarget:
    return SetupTarget(
        identifier=identifier,
        display_name=identifier.title(),
        path=Path(f"/tmp/{identifier}.txt") if detected else None,
        format_name="text",
        detected=detected,
        available=detected and status == "ok",
        readable=status in {"ok", "empty"},
        supported=True,
        enabled_by_default=selectable and detected,
        selectable=selectable,
        word_count=1 if detected else None,
        status=status,
        detail=detail,
    )


def _button_event(button_id: str):
    class _Button:
        id = button_id

    class _Event:
        button = _Button()

    return _Event()


class TestSetupTargetsScreenCoverage(unittest.IsolatedAsyncioTestCase):
    def _controller(self, discovery: SetupTargetDiscovery | None = None) -> TuiController:
        discovery = discovery or SetupTargetDiscovery(
            targets=(_target("chrome"), _target("firefox")),
            default_enabled=("chrome", "firefox"),
        )
        service = fake_service()
        service.discover_setup_targets = MagicMock(return_value=discovery)
        controller = TuiController(service, ProjectRef())
        controller.set_setup_wordlist(Path("/tmp/setup/wordlist.txt"))
        controller._setup_discovery = discovery
        controller._setup_selection = SetupSelection(frozenset({"chrome"}))
        return controller

    async def test_focus_navigation_and_refresh(self):
        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupTargetsScreen(controller, "detail"))
            await pilot.pause()
            screen = app.screen
            rows = list(screen.query(SetupTargetRowWidget))
            rows[0].focus()
            screen.action_focus_next()
            screen.action_focus_previous()
            screen.action_focus_previous()
            screen.action_toggle_focused()
            screen._start_refresh()
            await pilot.pause()
            await pilot.pause()
            self.assertIn("chrome", controller.setup_selected_targets)

    async def test_refresh_worker_error_and_stale_token(self):
        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupTargetsScreen(controller, "detail"))
            await pilot.pause()
            screen = app.screen
            running_worker = MagicMock()
            running_worker.is_running = True
            screen._refresh_worker = running_worker
            screen._start_refresh()
            worker = MagicMock()
            worker.state = WorkerState.RUNNING
            screen._refresh_worker = worker
            screen._on_refresh_worker_state(Worker.StateChanged(worker, WorkerState.RUNNING))
            worker.state = WorkerState.ERROR
            screen._on_refresh_worker_state(Worker.StateChanged(worker, WorkerState.ERROR))
            self.assertIn("failed", str(screen.query_one("#targets-status").render()))
            worker.state = WorkerState.SUCCESS
            worker.result = 0
            screen._refresh_token = 99
            screen._on_refresh_worker_state(Worker.StateChanged(worker, WorkerState.SUCCESS))
            worker.result = screen._refresh_token
            screen._on_refresh_worker_state(Worker.StateChanged(worker, WorkerState.SUCCESS))
            worker.result = 999
            screen._on_refresh_worker_state(Worker.StateChanged(worker, WorkerState.SUCCESS))
            await pilot.pause()

    async def test_preview_shows_none_enabled(self):
        discovery = SetupTargetDiscovery(
            targets=(_target("chrome"),),
            default_enabled=(),
        )
        controller = self._controller(discovery)
        controller._setup_selection = SetupSelection(frozenset())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupPreviewScreen(controller))
            await pilot.pause()
            content = str(app.screen.query_one("#preview-content").render())
            self.assertIn("(none)", content)

    async def test_setup_targets_widget_handlers(self):
        discovery = SetupTargetDiscovery(
            targets=(
                _target("chrome"),
                SetupTarget(
                    identifier="cursor",
                    display_name="Cursor",
                    path=Path("/tmp/cursor.txt"),
                    format_name="text",
                    detected=True,
                    available=False,
                    readable=False,
                    supported=True,
                    enabled_by_default=False,
                    selectable=False,
                    word_count=None,
                    status="corrupt",
                    detail="Corrupt dictionary",
                ),
            ),
            default_enabled=("chrome",),
        )
        controller = self._controller(discovery)
        controller._setup_selection = SetupSelection(frozenset())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupTargetsScreen(controller, "detail"))
            await pilot.pause()
            screen = app.screen
            screen.action_focus_next()
            screen.action_focus_previous()
            row = screen.query_one("#target-row-chrome", SetupTargetRowWidget)
            row.post_message(SetupTargetRowWidget.Toggled("chrome"))
            corrupt = screen.query_one("#target-row-cursor", SetupTargetRowWidget)
            corrupt_checkbox = corrupt.query_one("#target-checkbox-cursor")
            corrupt_checkbox.value = True
            corrupt._on_checkbox_changed(type("E", (), {"checkbox": corrupt_checkbox})())
            row.key_space()
            for button_id in ("btn-refresh", "btn-clear", "btn-continue"):
                screen.on_button_pressed(_button_event(button_id))
            await pilot.pause()
            self.assertFalse(corrupt_checkbox.value)
            self.assertIsNotNone(screen.query_one("#targets-status"))

    async def test_focus_navigation_without_rows(self):
        controller = self._controller(SetupTargetDiscovery(targets=(), default_enabled=()))
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupTargetsScreen(controller, "detail"))
            await pilot.pause()
            screen = app.screen
            screen.action_focus_next()
            screen.action_focus_previous()
            screen.action_toggle_focused()
            self.assertEqual(len(list(screen.query(SetupTargetRowWidget))), 0)

    async def test_focused_property_and_wrong_checkbox(self):
        from textual.widgets import Button

        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(SetupTargetsScreen(controller, "detail"))
            await pilot.pause()
            screen = app.screen
            row = screen.query_one("#target-row-chrome", SetupTargetRowWidget)
            with patch.object(type(screen), "focused", new_callable=PropertyMock) as focused:
                focused.return_value = None
                screen.action_focus_previous()
                screen.action_focus_next()
                focused.return_value = screen.query_one("#btn-back", Button)
                screen.action_focus_previous()
                screen.action_focus_next()
                focused.return_value = row
                row.focus()
                screen.action_focus_next()
                screen.action_focus_previous()
                screen.action_toggle_focused()
            wrong_event = MagicMock()
            wrong_event.checkbox = MagicMock(id="target-checkbox-other")
            row._on_checkbox_changed(wrong_event)
            screen.on_button_pressed(_button_event("btn-select-available"))
            self.assertIn("chrome", controller.setup_selected_targets)


class TestControllerSetupCoverage(unittest.TestCase):
    def test_setup_helpers_without_session(self) -> None:
        controller = TuiController(fake_service(), CliOptions())
        self.assertEqual(controller.setup_selected_targets, ())
        self.assertEqual(controller.setup_selection().selected_target_ids, frozenset())
        with self.assertRaises(RuntimeError):
            controller.setup_target_discovery()
        self.assertFalse(controller.toggle_setup_target("chrome"))
        controller.select_available_setup_targets()
        controller.clear_setup_target_selection()

    def test_wordlist_reload_preserves_selection(self) -> None:
        discovery = SetupTargetDiscovery(
            targets=(
                SetupTarget(
                    identifier="chrome",
                    display_name="Chrome",
                    path=Path("/tmp/chrome.txt"),
                    format_name="text",
                    detected=True,
                    available=True,
                    readable=True,
                    supported=True,
                    enabled_by_default=True,
                    selectable=True,
                    word_count=1,
                    status="ok",
                    detail=None,
                ),
            ),
            default_enabled=("chrome",),
        )
        service = fake_service()
        service.discover_setup_targets = MagicMock(return_value=discovery)
        controller = TuiController(service, ProjectRef())
        wordlist = Path("/tmp/setup/wordlist.txt")
        controller.set_setup_wordlist(wordlist)
        controller._setup_selection = SetupSelection(frozenset())
        controller.set_setup_wordlist(wordlist)
        self.assertEqual(controller.setup_selection().selected_target_ids, frozenset())

    def test_load_discovery_without_wordlist(self) -> None:
        controller = TuiController(fake_service(), CliOptions())
        controller._load_setup_discovery(reset_selection=True)
        self.assertIsNone(controller._setup_discovery)


if __name__ == "__main__":
    unittest.main()
