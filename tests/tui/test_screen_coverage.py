"""Coverage tests for TUI worker callbacks and edge paths."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

from textual.widgets import Static
from textual.worker import WorkerState

from spell_sync.application.reports import (
    DoctorCheckView,
    DoctorSnapshot,
    PushPreview,
    StatusDetailSnapshot,
    TargetPreview,
    TargetStatusRow,
)
from spell_sync.cli_options import CliOptions
from spell_sync.exit_codes import ExitCode
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.dashboard import DashboardScreen
from spell_sync.tui.screens.doctor_screen import DoctorScreen
from spell_sync.tui.screens.preview_screen import PreviewScreen
from spell_sync.tui.screens.removals_screen import RemovalsScreen
from spell_sync.tui.screens.status_screen import StatusScreen
from tests.tui.fake_service import fake_service, sample_dashboard, sample_preview
from tests.tui.test_helpers import wait_for_text


def _static_text(screen, selector: str) -> str:
    return str(screen.query_one(selector, Static).render())


class TestScreenCoverage(unittest.IsolatedAsyncioTestCase):
    async def test_app_quit_hotkey(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            await wait_for_text(pilot, "#dashboard-summary", "Ready")
            await pilot.press("q")
            await pilot.pause()

    async def test_controller_status_helper(self):
        controller = TuiController(fake_service(), CliOptions())
        self.assertEqual(controller.status().wordlist_count, 3)

    async def test_dashboard_mount_failure_and_worker_paths(self):
        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(60, 20)) as pilot:
            await wait_for_text(pilot, "#narrow-warning", "80x24")
            screen = app.screen
            assert isinstance(screen, DashboardScreen)
            with patch.object(controller, "dashboard", side_effect=RuntimeError("boom")):
                screen.on_mount()
            self.assertIn("failed", _static_text(screen, "#dashboard-summary"))

            screen._active_token = screen._begin_load()
            with patch.object(controller, "dashboard", side_effect=RuntimeError("boom")):
                result = screen.load_dashboard_worker.__wrapped__(screen)
            self.assertIsNone(result)

            screen.on_load_dashboard_worker_state_changed(
                SimpleNamespace(state=WorkerState.RUNNING, worker=SimpleNamespace(result=None))
            )
            screen.on_load_dashboard_worker_state_changed(
                SimpleNamespace(state=WorkerState.ERROR, worker=SimpleNamespace(result=None))
            )
            self.assertIn("unavailable", _static_text(screen, "#dashboard-summary"))

            stale = screen._load_generation
            screen._active_token = stale - 1
            screen.on_load_dashboard_worker_state_changed(
                SimpleNamespace(
                    state=WorkerState.SUCCESS,
                    worker=SimpleNamespace(result=sample_dashboard()),
                )
            )
            screen._active_token = stale
            screen.on_load_dashboard_worker_state_changed(
                SimpleNamespace(state=WorkerState.SUCCESS, worker=SimpleNamespace(result=None))
            )
            self.assertIn("failed", _static_text(screen, "#dashboard-summary"))
            screen.on_load_dashboard_worker_state_changed(
                SimpleNamespace(
                    state=WorkerState.SUCCESS,
                    worker=SimpleNamespace(result=sample_dashboard()),
                )
            )
            stale_token = screen._active_token
            screen._active_token = stale_token - 1
            screen.on_load_dashboard_worker_state_changed(
                SimpleNamespace(state=WorkerState.ERROR, worker=SimpleNamespace(result=None))
            )
            screen._active_token = stale_token
            for button_id in ("btn-pull", "btn-push", "btn-recovery", "btn-history"):
                screen.on_button_pressed(SimpleNamespace(button=SimpleNamespace(id=button_id)))
            screen.on_button_pressed(
                SimpleNamespace(button=SimpleNamespace(id="btn-review-update"))
            )
            screen.on_button_pressed(SimpleNamespace(button=SimpleNamespace(id="btn-health")))
            screen.on_load_dashboard_worker_state_changed(
                SimpleNamespace(state=WorkerState.CANCELLED, worker=SimpleNamespace(result=None))
            )
            await pilot.pause()

    async def test_status_render_branches_and_workers(self):
        detail = StatusDetailSnapshot(
            wordlist_path="/tmp/w.txt",
            project_dir="/tmp",
            config_paths=(),
            wordlist_count=3,
            targets=(
                TargetStatusRow(
                    name="chrome",
                    enabled=True,
                    available=True,
                    read_status="ok",
                    path="/tmp/chrome.txt",
                    format="text",
                    word_count=5,
                    detail="readable",
                ),
            ),
            skipped_unreadable=("offline",),
            skipped_corrupt=("broken",),
            destructive_risk="large removal set",
        )
        controller = TuiController(fake_service(status_detail=detail), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.switch_screen(StatusScreen(controller))
            await wait_for_text(pilot, "#status-summary", "destructive")
            screen = app.screen
            assert isinstance(screen, StatusScreen)

            empty_targets = StatusDetailSnapshot(
                wordlist_path="/tmp/w.txt",
                project_dir="/tmp",
                config_paths=("/tmp/spell-sync.toml",),
                wordlist_count=3,
                targets=(),
                skipped_unreadable=(),
                skipped_corrupt=(),
            )
            screen._render_snapshot(empty_targets)
            self.assertIn("No targets configured", _static_text(screen, "#status-summary"))

            with patch.object(controller, "status_detail", side_effect=RuntimeError("boom")):
                screen.on_mount()
            self.assertIn("failed", _static_text(screen, "#status-summary"))

            screen._active_token = screen._begin_load()
            with patch.object(controller, "status_detail", side_effect=RuntimeError("boom")):
                fallback = screen.load_status_worker.__wrapped__(screen)
            self.assertEqual(fallback.load_error, "Status could not be loaded.")

            screen.on_load_status_worker_state_changed(
                SimpleNamespace(state=WorkerState.RUNNING, worker=SimpleNamespace(result=None))
            )
            screen.on_load_status_worker_state_changed(
                SimpleNamespace(state=WorkerState.ERROR, worker=SimpleNamespace(result=None))
            )
            self.assertIn("unavailable", _static_text(screen, "#status-summary"))

            stale = screen._load_generation
            screen._active_token = stale - 1
            screen.on_load_status_worker_state_changed(
                SimpleNamespace(
                    state=WorkerState.SUCCESS,
                    worker=SimpleNamespace(result=detail),
                )
            )
            screen._active_token = stale
            screen.on_load_status_worker_state_changed(
                SimpleNamespace(
                    state=WorkerState.SUCCESS,
                    worker=SimpleNamespace(result=detail),
                )
            )
            screen.on_load_status_worker_state_changed(
                SimpleNamespace(state=WorkerState.CANCELLED, worker=SimpleNamespace(result=None))
            )
            screen.on_button_pressed(SimpleNamespace(button=SimpleNamespace(id="btn-refresh")))
            await pilot.press("escape")
            await pilot.pause()

    async def test_preview_render_branches_and_workers(self):
        preview = sample_preview(
            skipped=("offline",),
            corrupt=("broken",),
            warnings=("watch out",),
        )
        controller = TuiController(fake_service(preview=preview), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.switch_screen(PreviewScreen(controller))
            await wait_for_text(pilot, "#preview-content", "Skipped")
            screen = app.screen
            assert isinstance(screen, PreviewScreen)

            blocked = PushPreview(
                prepared=None,
                targets=(),
                additions=0,
                removals=0,
                warnings=(),
                created_at="",
                plan_identifier="blocked",
                targets_to_update=0,
                unchanged=0,
                skipped=(),
                corrupt=(),
                blocked=(),
                prepare_error=ExitCode.PUSH_ABORT,
            )
            screen._render_preview(blocked)
            self.assertIn("Plan blocked", _static_text(screen, "#preview-content"))

            unreadable = PushPreview(
                prepared=None,
                targets=(),
                additions=0,
                removals=0,
                warnings=(),
                created_at="",
                plan_identifier="unavailable",
                targets_to_update=0,
                unchanged=0,
                skipped=(),
                corrupt=(),
                blocked=(),
                wordlist_error=ExitCode.PUSH_ABORT,
            )
            screen._render_preview(unreadable)
            self.assertIn("Preview unavailable", _static_text(screen, "#preview-content"))

            with patch.object(controller, "preview", side_effect=RuntimeError("boom")):
                screen.on_mount()
            self.assertIn("failed", _static_text(screen, "#preview-content"))

            screen._preview = None
            screen.action_view_removals()

            screen._preview = preview
            real_query_one = screen.query_one

            def query_with_empty_table(selector, widget_type=None):
                if selector == "#preview-table":
                    mock_table = MagicMock()
                    mock_table.row_count = 0
                    return mock_table
                if widget_type is None:
                    return real_query_one(selector)
                return real_query_one(selector, widget_type)

            with patch.object(screen, "query_one", side_effect=query_with_empty_table):
                self.assertEqual(screen._selected_target(), preview.targets[0])

            def query_with_invalid_cursor(selector, widget_type=None):
                if selector == "#preview-table":
                    mock_table = MagicMock()
                    mock_table.row_count = 1
                    mock_table.cursor_row = -1
                    return mock_table
                if widget_type is None:
                    return real_query_one(selector)
                return real_query_one(selector, widget_type)

            with patch.object(screen, "query_one", side_effect=query_with_invalid_cursor):
                self.assertEqual(screen._selected_target(), preview.targets[0])

            multi_target = sample_preview(
                targets=(
                    TargetPreview(
                        name="chrome",
                        additions=1,
                        removals=0,
                        status="Ready",
                        removal_words=frozenset(),
                    ),
                    TargetPreview(
                        name="cursor",
                        additions=1,
                        removals=0,
                        status="Ready",
                        removal_words=frozenset(),
                    ),
                ),
                additions=2,
            )
            screen._preview = multi_target
            screen._render_preview(multi_target)

            def query_with_valid_cursor(selector, widget_type=None):
                if selector == "#preview-table":
                    mock_table = MagicMock()
                    mock_table.row_count = 2
                    mock_table.cursor_row = 1
                    return mock_table
                if widget_type is None:
                    return real_query_one(selector)
                return real_query_one(selector, widget_type)

            with patch.object(screen, "query_one", side_effect=query_with_valid_cursor):
                self.assertEqual(screen._selected_target(), multi_target.targets[1])

            screen._active_token = screen._begin_load()
            with patch.object(controller, "preview", side_effect=RuntimeError("boom")):
                fallback = screen.load_preview_worker.__wrapped__(screen)
            self.assertEqual(fallback.plan_identifier, "error")

            screen.on_load_preview_worker_state_changed(
                SimpleNamespace(state=WorkerState.RUNNING, worker=SimpleNamespace(result=None))
            )
            screen.on_load_preview_worker_state_changed(
                SimpleNamespace(state=WorkerState.ERROR, worker=SimpleNamespace(result=None))
            )
            with patch.object(
                type(screen),
                "is_mounted",
                new_callable=PropertyMock,
                return_value=False,
            ):
                screen.on_load_preview_worker_state_changed(
                    SimpleNamespace(state=WorkerState.ERROR, worker=SimpleNamespace(result=None))
                )
            self.assertIn("unavailable", _static_text(screen, "#preview-content"))

            stale = screen._load_generation
            screen._active_token = stale - 1
            screen.on_load_preview_worker_state_changed(
                SimpleNamespace(
                    state=WorkerState.SUCCESS,
                    worker=SimpleNamespace(result=preview),
                )
            )
            screen._active_token = stale
            screen.on_load_preview_worker_state_changed(
                SimpleNamespace(
                    state=WorkerState.SUCCESS,
                    worker=SimpleNamespace(result=preview),
                )
            )
            screen.on_load_preview_worker_state_changed(
                SimpleNamespace(state=WorkerState.CANCELLED, worker=SimpleNamespace(result=None))
            )
            screen.on_button_pressed(
                SimpleNamespace(button=SimpleNamespace(id="btn-view-removals"))
            )
            await pilot.press("escape")
            await pilot.pause()

    async def test_doctor_render_branches_and_workers(self):
        doctor = DoctorSnapshot(
            checks=(
                DoctorCheckView(
                    group="Project",
                    level="failed",
                    title="Broken config",
                    detail="config is broken",
                    suggested_action="spell-sync config-check",
                ),
            ),
            has_errors=True,
        )
        controller = TuiController(fake_service(doctor=doctor), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.switch_screen(DoctorScreen(controller))
            await wait_for_text(pilot, "#doctor-summary", "blocking issues")
            screen = app.screen
            assert isinstance(screen, DoctorScreen)

            with patch.object(controller, "doctor", side_effect=RuntimeError("boom")):
                screen.on_mount()
            self.assertIn("failed", _static_text(screen, "#doctor-summary"))

            screen._active_token = screen._begin_load()
            with patch.object(controller, "doctor", side_effect=RuntimeError("boom")):
                fallback = screen.load_doctor_worker.__wrapped__(screen)
            self.assertEqual(fallback.load_error, "Doctor report could not be loaded.")

            screen.on_load_doctor_worker_state_changed(
                SimpleNamespace(state=WorkerState.RUNNING, worker=SimpleNamespace(result=None))
            )
            screen.on_load_doctor_worker_state_changed(
                SimpleNamespace(state=WorkerState.ERROR, worker=SimpleNamespace(result=None))
            )
            self.assertIn("unavailable", _static_text(screen, "#doctor-summary"))

            stale = screen._load_generation
            screen._active_token = stale - 1
            screen.on_load_doctor_worker_state_changed(
                SimpleNamespace(
                    state=WorkerState.SUCCESS,
                    worker=SimpleNamespace(result=doctor),
                )
            )
            screen._active_token = stale
            screen.on_load_doctor_worker_state_changed(
                SimpleNamespace(
                    state=WorkerState.SUCCESS,
                    worker=SimpleNamespace(result=doctor),
                )
            )
            screen.on_load_doctor_worker_state_changed(
                SimpleNamespace(state=WorkerState.CANCELLED, worker=SimpleNamespace(result=None))
            )
            screen.on_button_pressed(SimpleNamespace(button=SimpleNamespace(id="btn-run-doctor")))
            await pilot.press("escape")
            await pilot.pause()

    async def test_removals_empty_and_populated(self):
        app = SpellSyncApp(TuiController(fake_service(), CliOptions()))
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(RemovalsScreen("chrome", frozenset()))
            await pilot.pause()
            app.pop_screen()
            app.push_screen(RemovalsScreen("chrome", frozenset({"alpha"})))
            await pilot.press("escape")
            await pilot.pause()


if __name__ == "__main__":
    unittest.main()
