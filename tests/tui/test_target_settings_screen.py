"""TUI tests for post-setup target settings screens."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock

from spell_sync.application.requests import ProjectRef
from spell_sync.project_setup.discovery import SetupTarget
from spell_sync.project_setup.selection import SetupSelection
from spell_sync.project_setup.target_settings import (
    PreparedTargetSettingsUpdate,
    TargetSettingsSnapshot,
)
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.setup_targets_screen import SetupTargetRowWidget
from spell_sync.tui.screens.target_settings_screen import (
    TargetSettingsReviewScreen,
    TargetSettingsScreen,
)
from tests.tui.fake_service import fake_service


def _target(
    identifier: str,
    *,
    selectable: bool = True,
    enabled: bool = False,
    status: str = "ok",
    detail: str | None = None,
) -> SetupTarget:
    return SetupTarget(
        identifier=identifier,
        display_name=identifier.title(),
        path=Path(f"/tmp/{identifier}.txt"),
        format_name="text",
        detected=True,
        available=status == "ok",
        readable=status in {"ok", "empty"},
        supported=True,
        enabled_by_default=selectable,
        selectable=selectable,
        word_count=3,
        status=status,
        detail=detail,
        enabled=enabled,
    )


def _snapshot(*targets: SetupTarget) -> TargetSettingsSnapshot:
    enabled = frozenset(target.identifier for target in targets if target.enabled)
    return TargetSettingsSnapshot(
        config_path=Path("/tmp/project/spell-sync.toml"),
        wordlist_path=Path("/tmp/project/wordlist.txt"),
        targets=targets,
        enabled_target_ids=enabled,
    )


def _button_event(button_id: str):
    class _Button:
        id = button_id

    class _Event:
        button = _Button()

    return _Event()


class TestTargetSettingsScreen(unittest.IsolatedAsyncioTestCase):
    def _controller(self, snapshot: TargetSettingsSnapshot) -> TuiController:
        service = fake_service()
        service.load_target_settings = MagicMock(return_value=snapshot)
        service.prepare_target_settings_update = MagicMock(
            return_value=PreparedTargetSettingsUpdate(
                update_id="update-1",
                config_path=snapshot.config_path,
                wordlist_path=snapshot.wordlist_path,
                selected_target_ids=frozenset({"chrome", "edge"}),
                previous_target_ids=snapshot.enabled_target_ids,
                enabled_target_ids=frozenset({"edge"}),
                disabled_target_ids=frozenset(),
                rendered_config_bytes=b"[dictionaries]\n",
                config_fingerprint_before="abc",
                warnings=(),
                can_execute=True,
            )
        )
        return TuiController(service, ProjectRef(wordlist=snapshot.wordlist_path))

    async def test_toggle_target_updates_selection(self) -> None:
        snapshot = _snapshot(
            _target("chrome", enabled=True),
            _target("edge"),
            _target("corrupt", selectable=False, enabled=True, status="corrupt", detail="Corrupt"),
        )
        controller = self._controller(snapshot)
        app = SpellSyncApp(controller)
        async with app.run_test():
            await app.push_screen(TargetSettingsScreen(controller))
            screen = app.screen
            assert isinstance(screen, TargetSettingsScreen)
            screen._on_target_toggled(SetupTargetRowWidget.Toggled("edge"))
            assert "edge" in controller.target_settings_selection().selected_target_ids

    async def test_corrupt_target_cannot_toggle(self) -> None:
        snapshot = _snapshot(
            _target("chrome", enabled=True),
            _target("corrupt", selectable=False, enabled=True, status="corrupt"),
        )
        controller = self._controller(snapshot)
        app = SpellSyncApp(controller)
        async with app.run_test():
            await app.push_screen(TargetSettingsScreen(controller))
            screen = app.screen
            assert isinstance(screen, TargetSettingsScreen)
            before = controller.target_settings_selection().selected_target_ids
            screen._on_target_toggled(SetupTargetRowWidget.Toggled("corrupt"))
            assert controller.target_settings_selection().selected_target_ids == before

    async def test_clear_and_select_available(self) -> None:
        snapshot = _snapshot(_target("chrome", enabled=True), _target("edge"))
        controller = self._controller(snapshot)
        app = SpellSyncApp(controller)
        async with app.run_test():
            await app.push_screen(TargetSettingsScreen(controller))
            screen = app.screen
            assert isinstance(screen, TargetSettingsScreen)
            screen.on_button_pressed(_button_event("btn-select-available"))
            assert controller.target_settings_selection().selected_target_ids == frozenset(
                {"chrome", "edge"}
            )
            screen.on_button_pressed(_button_event("btn-clear"))
            assert controller.target_settings_selection().selected_target_ids == frozenset()

    async def test_back_keeps_draft(self) -> None:
        snapshot = _snapshot(_target("chrome", enabled=True), _target("edge"))
        controller = self._controller(snapshot)
        app = SpellSyncApp(controller)
        async with app.run_test() as pilot:
            await app.push_screen(TargetSettingsScreen(controller))
            screen = app.screen
            assert isinstance(screen, TargetSettingsScreen)
            controller.toggle_target_settings_target("edge")
            await app.push_screen(TargetSettingsReviewScreen(controller))
            await pilot.click("#btn-back")
            assert "edge" in controller.target_settings_selection().selected_target_ids
            assert isinstance(app.screen, TargetSettingsScreen)

    async def test_review_shows_changes(self) -> None:
        snapshot = _snapshot(_target("chrome", enabled=True), _target("edge"))
        controller = self._controller(snapshot)
        app = SpellSyncApp(controller)
        async with app.run_test():
            await app.push_screen(TargetSettingsScreen(controller))
            screen = app.screen
            assert isinstance(screen, TargetSettingsScreen)
            controller.toggle_target_settings_target("edge")
            await app.push_screen(TargetSettingsReviewScreen(controller))
            review = app.screen
            assert isinstance(review, TargetSettingsReviewScreen)
            text = review.query_one("#review-content").render().plain
            assert "Enable:" in text
            assert "No application dictionaries will be changed." in text

    async def test_refresh_keeps_stale_selection_when_target_removed(self) -> None:
        snapshot = _snapshot(_target("chrome", enabled=True), _target("edge", enabled=True))
        controller = self._controller(snapshot)
        controller._target_settings_selection = SetupSelection(frozenset({"chrome", "edge"}))
        refreshed = _snapshot(_target("chrome", enabled=True))
        controller._service.load_target_settings = MagicMock(return_value=refreshed)
        app = SpellSyncApp(controller)
        async with app.run_test():
            await app.push_screen(TargetSettingsScreen(controller))
            screen = app.screen
            assert isinstance(screen, TargetSettingsScreen)
            controller.refresh_target_settings_discovery()
            selected = controller.target_settings_selection().selected_target_ids
            assert selected == frozenset({"chrome"})

    async def test_open_details_from_focused_row(self) -> None:
        snapshot = _snapshot(_target("chrome", enabled=True))
        controller = self._controller(snapshot)
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await app.push_screen(TargetSettingsScreen(controller))
            screen = app.screen
            assert isinstance(screen, TargetSettingsScreen)
            row = screen.query_one("#target-row-chrome", SetupTargetRowWidget)
            row.focus()
            await pilot.press("enter")
            await pilot.pause()
            from spell_sync.tui.screens.target_details_screen import TargetDetailsScreen

            self.assertIsInstance(app.screen, TargetDetailsScreen)


if __name__ == "__main__":
    unittest.main()
