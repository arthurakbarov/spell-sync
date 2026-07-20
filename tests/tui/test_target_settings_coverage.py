"""Additional target settings screen coverage."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

from textual.worker import WorkerState

from spell_sync.application.reports import OperationOutcome, OperationReport
from spell_sync.application.requests import ProjectRef
from spell_sync.project_setup.discovery import SetupTarget
from spell_sync.project_setup.target_settings import (
    PreparedTargetSettingsUpdate,
    TargetSettingsSnapshot,
)
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.dashboard import DashboardScreen
from spell_sync.tui.screens.operation_screen import OperationScreen
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


class TestTargetSettingsScreenCoverage(unittest.IsolatedAsyncioTestCase):
    def _controller(self, snapshot: TargetSettingsSnapshot | None = None) -> TuiController:
        snapshot = snapshot or _snapshot(_target("chrome", enabled=True), _target("edge"))
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

    async def test_focus_navigation_refresh_and_escape(self):
        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            await app.push_screen(TargetSettingsScreen(controller))
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, TargetSettingsScreen)
            rows = list(screen.query(SetupTargetRowWidget))
            rows[0].focus()
            screen.action_focus_next()
            screen.action_focus_previous()
            screen.action_focus_previous()
            screen.action_toggle_focused()
            screen._start_refresh()
            await pilot.pause()
            await pilot.pause()
            screen.action_back()

    async def test_focus_navigation_without_rows(self):
        controller = self._controller(_snapshot())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            await app.push_screen(TargetSettingsScreen(controller))
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, TargetSettingsScreen)
            screen.action_focus_next()
            screen.action_focus_previous()
            screen.action_toggle_focused()

    async def test_refresh_error_and_stale_token(self):
        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            await app.push_screen(TargetSettingsScreen(controller))
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, TargetSettingsScreen)
            controller.refresh_target_settings_discovery = MagicMock(
                side_effect=RuntimeError("boom"),
            )
            with patch.object(screen, "_refresh_targets_worker") as worker:
                worker.return_value = 999
                screen._refresh_token = 1
                screen._refresh_worker = worker
                screen._on_refresh_worker_state(
                    type(
                        "E",
                        (),
                        {
                            "worker": worker,
                            "state": WorkerState.ERROR,
                        },
                    )()
                )
            screen._refresh_token = 1
            screen._on_refresh_worker_state(
                type(
                    "E",
                    (),
                    {
                        "worker": MagicMock(result=999),
                        "state": WorkerState.SUCCESS,
                    },
                )()
            )

    async def test_load_error_disables_actions(self):
        snapshot = TargetSettingsSnapshot(
            config_path=Path("/tmp/project/spell-sync.toml"),
            wordlist_path=Path("/tmp/project/wordlist.txt"),
            targets=(),
            enabled_target_ids=frozenset(),
            load_error="Invalid configuration",
        )
        controller = self._controller(snapshot)
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            await app.push_screen(TargetSettingsScreen(controller))
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, TargetSettingsScreen)
            self.assertTrue(screen.query_one("#btn-review").disabled)

    async def test_review_save_and_repeated_save(self):
        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            await app.push_screen(TargetSettingsReviewScreen(controller))
            await pilot.pause()
            review = app.screen
            assert isinstance(review, TargetSettingsReviewScreen)
            review.on_button_pressed(_button_event("btn-save"))
            review.on_button_pressed(_button_event("btn-save"))
            await pilot.pause()

    async def test_review_cannot_execute(self):
        controller = self._controller()
        controller._service.prepare_target_settings_update = MagicMock(
            return_value=PreparedTargetSettingsUpdate(
                update_id="update-1",
                config_path=Path("/tmp/project/spell-sync.toml"),
                wordlist_path=Path("/tmp/project/wordlist.txt"),
                selected_target_ids=frozenset({"chrome"}),
                previous_target_ids=frozenset({"chrome"}),
                enabled_target_ids=frozenset(),
                disabled_target_ids=frozenset(),
                rendered_config_bytes=b"",
                config_fingerprint_before="abc",
                warnings=("No configuration changes to apply.",),
                can_execute=False,
            )
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            await app.push_screen(TargetSettingsReviewScreen(controller))
            await pilot.pause()
            review = app.screen
            assert isinstance(review, TargetSettingsReviewScreen)
            self.assertTrue(review.query_one("#btn-save").disabled)

    async def test_dashboard_targets_navigation(self):
        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            await app.push_screen(DashboardScreen(controller))
            await pilot.pause()
            dashboard = app.screen
            assert isinstance(dashboard, DashboardScreen)
            dashboard.action_open_targets()
            await pilot.pause()
            self.assertIsInstance(app.screen, TargetSettingsScreen)

    async def test_operation_targets_flow(self):
        prepared = PreparedTargetSettingsUpdate(
            update_id="update-1",
            config_path=Path("/tmp/project/spell-sync.toml"),
            wordlist_path=Path("/tmp/project/wordlist.txt"),
            selected_target_ids=frozenset({"edge"}),
            previous_target_ids=frozenset({"chrome"}),
            enabled_target_ids=frozenset({"edge"}),
            disabled_target_ids=frozenset({"chrome"}),
            rendered_config_bytes=b"[dictionaries]\n",
            config_fingerprint_before="abc",
            warnings=(),
            can_execute=True,
        )
        controller = self._controller()
        controller._service.build_target_settings_report = MagicMock(
            return_value=OperationReport(
                operation="targets",
                outcome=OperationOutcome.COMPLETED,
                title="Configuration updated",
                summary="Enabled: Edge",
            )
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            await app.push_screen(
                OperationScreen(
                    controller,
                    operation="targets",
                    target_settings_prepared=prepared,
                )
            )
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()

    async def test_row_widget_meta_lines(self):
        target = _target(
            "broken",
            selectable=False,
            enabled=True,
            status="corrupt",
            detail="Corrupt dictionary",
        )
        row = SetupTargetRowWidget(target, selected=True, row_index=0)
        async with SpellSyncApp(self._controller()).run_test(size=(100, 40)) as pilot:
            await pilot.app.mount(row)
            await pilot.pause()
            row.on_focus()
            row.on_blur()
            row.set_selected(False)

    async def test_dashboard_targets_button(self):
        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            await app.push_screen(DashboardScreen(controller))
            await pilot.pause()
            dashboard = app.screen
            assert isinstance(dashboard, DashboardScreen)
            dashboard.on_button_pressed(_button_event("btn-targets"))
            await pilot.pause()
            self.assertIsInstance(app.screen, TargetSettingsScreen)

    async def test_controller_target_settings_helpers(self):
        controller = self._controller()
        controller.clear_target_settings_session()
        controller.load_target_settings()
        controller.target_settings_discovery()
        controller._target_settings_selection = None
        self.assertFalse(controller.toggle_target_settings_target("edge"))
        controller.select_available_target_settings()
        controller.clear_target_settings_selection()
        snapshot = TargetSettingsSnapshot(
            config_path=Path("/tmp/project/spell-sync.toml"),
            wordlist_path=Path("/tmp/project/wordlist.txt"),
            targets=(_target("chrome", enabled=True),),
            enabled_target_ids=frozenset({"chrome"}),
            load_error="broken",
        )
        controller._service.load_target_settings = MagicMock(return_value=snapshot)
        error = controller.refresh_target_settings_discovery()
        self.assertEqual(error, "broken")

    async def test_refresh_stale_token_and_error_state(self):
        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            await app.push_screen(TargetSettingsScreen(controller))
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, TargetSettingsScreen)
            worker = MagicMock()
            worker.result = (999, None)
            screen._refresh_worker = worker
            screen._refresh_token = 1
            screen._on_refresh_worker_state(
                type("E", (), {"worker": worker, "state": WorkerState.SUCCESS})()
            )
            worker.result = "not-a-tuple"
            screen._on_refresh_worker_state(
                type("E", (), {"worker": worker, "state": WorkerState.SUCCESS})()
            )
            screen._on_refresh_worker_state(
                type("E", (), {"worker": worker, "state": WorkerState.ERROR})()
            )

    async def test_focus_with_active_row(self):
        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            await app.push_screen(TargetSettingsScreen(controller))
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, TargetSettingsScreen)
            rows = list(screen.query(SetupTargetRowWidget))
            with patch.object(
                type(screen),
                "focused",
                new_callable=PropertyMock,
                return_value=rows[1],
            ):
                screen.action_focus_next()
                screen.action_focus_previous()
                screen.action_toggle_focused()

    async def test_button_handlers(self):
        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            await app.push_screen(TargetSettingsScreen(controller))
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, TargetSettingsScreen)
            with patch.object(screen, "_start_refresh") as refresh:
                screen.on_button_pressed(_button_event("btn-refresh"))
                refresh.assert_called_once()
            with patch.object(screen, "_sync_checkboxes") as sync:
                screen.on_button_pressed(_button_event("btn-select-available"))
                screen.on_button_pressed(_button_event("btn-clear"))
                self.assertEqual(sync.call_count, 2)
            with patch.object(screen.app, "push_screen") as push:
                screen.on_button_pressed(_button_event("btn-review"))
                push.assert_called_once()

    async def test_refresh_rerender_on_load_error(self):
        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            await app.push_screen(TargetSettingsScreen(controller))
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, TargetSettingsScreen)
            worker = MagicMock()
            worker.result = (screen._refresh_token, "Invalid configuration")
            screen._refresh_worker = worker
            with patch.object(screen, "_render_targets") as render:
                screen._on_refresh_worker_state(
                    type("E", (), {"worker": worker, "state": WorkerState.SUCCESS})()
                )
                render.assert_called_once()

    async def test_review_disabled_list_and_none_prepared(self):
        controller = self._controller()
        controller._service.prepare_target_settings_update = MagicMock(
            return_value=PreparedTargetSettingsUpdate(
                update_id="update-1",
                config_path=Path("/tmp/project/spell-sync.toml"),
                wordlist_path=Path("/tmp/project/wordlist.txt"),
                selected_target_ids=frozenset(),
                previous_target_ids=frozenset({"chrome"}),
                enabled_target_ids=frozenset(),
                disabled_target_ids=frozenset({"chrome"}),
                rendered_config_bytes=b"",
                config_fingerprint_before="abc",
                warnings=("warn",),
                can_execute=True,
            )
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            await app.push_screen(TargetSettingsReviewScreen(controller))
            await pilot.pause()
            review = app.screen
            assert isinstance(review, TargetSettingsReviewScreen)
            review._prepared = None
            review._render_review()

    async def test_review_action_back(self):
        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            await app.push_screen(TargetSettingsReviewScreen(controller))
            await pilot.pause()
            review = app.screen
            assert isinstance(review, TargetSettingsReviewScreen)
            review.action_back()

    async def test_selection_screen_escape_and_running_refresh_guard(self):
        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            await app.push_screen(TargetSettingsScreen(controller))
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, TargetSettingsScreen)
            screen._refresh_worker = MagicMock(is_running=True)
            screen._start_refresh()
            screen.on_button_pressed(_button_event("btn-back"))
            screen.action_back()

    async def test_row_widget_checkbox_paths(self):
        target = _target("chrome", enabled=True)
        row = SetupTargetRowWidget(target, selected=False, row_index=0)
        async with SpellSyncApp(self._controller()).run_test(size=(100, 40)) as pilot:
            await pilot.app.mount(row)
            await pilot.pause()
            checkbox = row.query_one("#target-checkbox-chrome")
            checkbox.value = True
            row._on_checkbox_changed(type("E", (), {"checkbox": checkbox})())
            corrupt = _target(
                "bad",
                selectable=False,
                enabled=True,
                status="corrupt",
                detail="Corrupt dictionary",
            )
            bad_row = SetupTargetRowWidget(corrupt, selected=True, row_index=1)
            await pilot.app.mount(bad_row)
            await pilot.pause()
            bad_checkbox = bad_row.query_one("#target-checkbox-bad")
            bad_checkbox.value = False
            bad_row._on_checkbox_changed(type("E", (), {"checkbox": bad_checkbox})())

    async def test_row_widget_meta_without_path(self):
        target = SetupTarget(
            identifier="missing",
            display_name="Missing",
            path=None,
            format_name="text",
            detected=False,
            available=False,
            readable=False,
            supported=True,
            enabled_by_default=False,
            selectable=False,
            word_count=None,
            status="missing",
            detail=None,
            enabled=False,
        )
        row = SetupTargetRowWidget(target, selected=False, row_index=0)
        self.assertIn("Not detected", "\n".join(row._meta_lines()))


if __name__ == "__main__":
    unittest.main()
