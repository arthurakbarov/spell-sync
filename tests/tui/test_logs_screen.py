"""TUI logs screen tests."""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from textual.widgets import DataTable, Static
from textual.worker import WorkerState

from spell_sync.application.requests import ProjectRef
from spell_sync.diagnostics.history_record import OperationHistoryRecord
from spell_sync.diagnostics.types import (
    HistoryClearResult,
    OperationHistorySnapshot,
    TechnicalLogSnapshot,
)
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.dashboard import DashboardScreen
from spell_sync.tui.screens.logs_screen import (
    ClearHistoryConfirmScreen,
    HistoryDetailsScreen,
    LogsScreen,
    TechnicalLogScreen,
    _summary_line,
)
from tests.tui.fake_service import fake_service


def _record(**overrides) -> OperationHistoryRecord:
    base = OperationHistoryRecord(
        schema_version=1,
        record_id="rec-1",
        timestamp=datetime(2026, 7, 18, 14, 32, tzinfo=timezone.utc),
        operation="push",
        outcome="completed",
        duration_ms=812,
        updated_targets=5,
        warnings=1,
    )
    if overrides:
        return replace(base, **overrides)
    return base


class TestLogsScreen(unittest.IsolatedAsyncioTestCase):
    def _controller(self, **history_kwargs) -> TuiController:
        service = fake_service()
        service.load_operation_history = lambda **kwargs: OperationHistorySnapshot(
            records=history_kwargs.get("records", (_record(),)),
            malformed_lines=history_kwargs.get("malformed_lines", 1),
        )
        service.read_technical_log_tail = lambda **kwargs: TechnicalLogSnapshot(
            path=Path("/tmp/spell-sync.log"),
            lines=("push started",),
            truncated=history_kwargs.get("truncated", False),
            detail=history_kwargs.get("detail"),
        )
        service.clear_operation_history = lambda: history_kwargs.get(
            "clear_result",
            HistoryClearResult(ok=True),
        )
        return TuiController(service, ProjectRef())

    async def _wait_for_rows(self, pilot, app, *, minimum: int = 1) -> int:
        row_count = 0
        for _ in range(30):
            await pilot.pause()
            row_count = app.screen.query_one("#history-table", DataTable).row_count
            if row_count >= minimum:
                break
        return row_count

    async def test_logs_screen_renders_history(self):
        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            app.push_screen(LogsScreen(controller))
            row_count = await self._wait_for_rows(pilot, app)
            self.assertEqual(row_count, 1)

    async def test_empty_history_state(self):
        controller = self._controller(records=(), malformed_lines=0)
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            app.push_screen(LogsScreen(controller))
            await self._wait_for_rows(pilot, app, minimum=0)
            status = str(app.screen.query_one("#logs-status", Static).render())
            self.assertIn("No completed operations", status)

    async def test_dashboard_logs_button_opens_screen(self):
        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 48)) as pilot:
            app.push_screen(DashboardScreen(controller))
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, DashboardScreen)
            screen.on_button_pressed(SimpleNamespace(button=SimpleNamespace(id="btn-history")))
            await pilot.pause()
            self.assertIsInstance(app.screen, LogsScreen)

    async def test_operation_filter_reload(self):
        from textual.widgets import Select

        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            app.push_screen(LogsScreen(controller))
            await self._wait_for_rows(pilot, app)
            select = app.screen.query_one("#filter-operation", Select)
            select.value = "pull"
            select.post_message(Select.Changed(select, select.value))
            await pilot.pause()
            await pilot.pause()
            self.assertIsInstance(app.screen, LogsScreen)

    async def test_history_details_and_technical_log(self):
        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            app.push_screen(HistoryDetailsScreen(_record()))
            await pilot.pause()
            content = str(app.screen.query_one("#details-content").render())
            self.assertIn("812 ms", content)
            self.assertNotIn("alpha", content)
            app.pop_screen()
            app.push_screen(TechnicalLogScreen(controller))
            await pilot.pause()
            await pilot.pause()
            tech = str(app.screen.query_one("#tech-log-summary").render())
            self.assertIn("Technical log", tech)

    async def test_technical_log_truncated_marker(self):
        controller = self._controller(truncated=True, detail="read truncated")
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            app.push_screen(TechnicalLogScreen(controller))
            await pilot.pause()
            await pilot.pause()
            tech = str(app.screen.query_one("#tech-log-summary").render())
            self.assertIn("most recent part", tech)

    async def test_technical_json_line_renders_as_table_row(self):
        line = (
            '{"schemaVersion":1,"timestamp":"2026-07-18T14:32:00Z",'
            '"eventId":"push.completed","operation":"push","category":"lifecycle",'
            '"severity":"success","phase":"completed"}'
        )
        controller = self._controller()
        controller._service.read_technical_log_tail = lambda **kwargs: TechnicalLogSnapshot(
            path=Path("/tmp/spell-sync.log"),
            lines=(line,),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            app.push_screen(TechnicalLogScreen(controller))
            await pilot.pause()
            await pilot.pause()
            table = app.screen.query_one("#tech-log-table", DataTable)
            self.assertEqual(table.row_count, 1)

    async def test_clear_history_confirmation(self):
        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            app.push_screen(LogsScreen(controller))
            await self._wait_for_rows(pilot, app)
            await pilot.click("#btn-clear")
            await pilot.pause()
            self.assertIsInstance(app.screen, ClearHistoryConfirmScreen)
            await pilot.click("#btn-confirm")
            await pilot.pause()
            self.assertIsInstance(app.screen, LogsScreen)

    async def test_clear_history_failure(self):
        controller = self._controller(clear_result=HistoryClearResult(ok=False, detail="denied"))
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            app.push_screen(LogsScreen(controller))
            await self._wait_for_rows(pilot, app)
            await pilot.click("#btn-clear")
            await pilot.pause()
            await pilot.click("#btn-confirm")
            await pilot.pause()
            self.assertIsInstance(app.screen, LogsScreen)

    async def test_view_history_details_from_row(self):
        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            app.push_screen(LogsScreen(controller))
            await self._wait_for_rows(pilot, app)
            table = app.screen.query_one("#history-table", DataTable)
            table.focus()
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(app.screen, HistoryDetailsScreen)

    def test_summary_line_variants(self):
        pull = _summary_line(_record(operation="pull", outcome="completed", added_words=17))
        self.assertIn("17 added", pull)
        setup = _summary_line(_record(operation="setup", outcome="completed", created_files=2))
        self.assertIn("2 files", setup)
        recover = _summary_line(_record(operation="recover", outcome="completed", restored_files=3))
        self.assertIn("3 restored", recover)

    async def test_load_failure_shows_controlled_error(self):
        service = fake_service()
        service.load_operation_history = MagicMock(side_effect=RuntimeError("boom"))
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            app.push_screen(LogsScreen(controller))
            for _ in range(20):
                await pilot.pause()
                if "could not be loaded" in str(app.screen.query_one("#logs-status").render()):
                    break
            status = str(app.screen.query_one("#logs-status").render())
            self.assertIn("could not be loaded", status)

    async def test_logs_screen_actions(self):
        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            app.push_screen(LogsScreen(controller))
            await self._wait_for_rows(pilot, app)
            await pilot.click("#btn-refresh")
            await pilot.pause()
            await pilot.click("#btn-back")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, LogsScreen)

    async def test_doctor_opens_technical_log(self):
        from spell_sync.tui.screens.doctor_screen import DoctorScreen

        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            app.push_screen(DoctorScreen(controller))
            await pilot.pause()
            await pilot.click("#btn-tech-log")
            await pilot.pause()
            self.assertIsInstance(app.screen, TechnicalLogScreen)

    async def test_outcome_filter_reload(self):
        from textual.widgets import Select

        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            app.push_screen(LogsScreen(controller))
            await self._wait_for_rows(pilot, app)
            select = app.screen.query_one("#filter-outcome", Select)
            select.value = "completed_with_warnings"
            select.post_message(Select.Changed(select, select.value))
            await pilot.pause()
            await pilot.pause()

    async def test_clear_history_cancel(self):
        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            app.push_screen(LogsScreen(controller))
            await self._wait_for_rows(pilot, app)
            await pilot.click("#btn-clear")
            await pilot.pause()
            await pilot.click("#btn-cancel")
            await pilot.pause()
            self.assertIsInstance(app.screen, LogsScreen)

    async def test_history_details_all_fields(self):
        record = _record(
            skipped_targets=1,
            additions=2,
            removals=3,
            added_words=4,
            created_files=2,
            enabled_targets=1,
            transaction_id="transaction-abcdef",
            setup_id="setup-abcdef",
            warnings=2,
        )
        app = SpellSyncApp(self._controller())
        async with app.run_test(size=(100, 40)) as pilot:
            app.push_screen(HistoryDetailsScreen(record))
            await pilot.pause()
            content = str(app.screen.query_one("#details-content").render())
            self.assertIn("Targets skipped", content)
            self.assertIn("Words added", content)
            await pilot.click("#btn-back")
            await pilot.pause()

    async def test_technical_log_refresh_and_error(self):
        service = fake_service()
        calls = {"count": 0}

        def read_tail(**kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("fail")
            return TechnicalLogSnapshot(path=Path("/tmp/log"), lines=("ok",))

        service.read_technical_log_tail = read_tail
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            app.push_screen(TechnicalLogScreen(controller))
            for _ in range(15):
                await pilot.pause()
            await pilot.click("#btn-refresh")
            for _ in range(15):
                await pilot.pause()
            content = str(app.screen.query_one("#tech-log-summary").render())
            self.assertIn("Technical log", content)

    async def test_technical_log_back_button_pops_screen(self):
        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            app.push_screen(LogsScreen(controller))
            await self._wait_for_rows(pilot, app)
            app.push_screen(TechnicalLogScreen(controller))
            for _ in range(10):
                await pilot.pause()
            self.assertIsInstance(app.screen, TechnicalLogScreen)
            await pilot.click("#btn-back")
            for _ in range(5):
                await pilot.pause()
            self.assertIsInstance(app.screen, LogsScreen)

    def test_summary_line_default_detail(self):
        line = _summary_line(_record(operation="doctor", outcome="failed", updated_targets=0))
        self.assertIn("Failed", line)

    async def test_worker_error_and_stale_token_handlers(self):
        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            app.push_screen(LogsScreen(controller))
            await self._wait_for_rows(pilot, app)
            screen = app.screen
            assert isinstance(screen, LogsScreen)
            worker = MagicMock()
            worker.result = None
            event = MagicMock()
            event.worker = worker
            event.state = WorkerState.ERROR
            screen._worker = worker
            screen._on_worker_state(event)
            status = str(screen.query_one("#logs-status").render())
            self.assertIn("could not be loaded", status)
            event.state = WorkerState.SUCCESS
            event.worker.result = None
            screen._on_worker_state(event)
            event.worker.result = (screen._load_token, None)
            screen._on_worker_state(event)
            event.worker.result = (screen._load_token - 1, OperationHistorySnapshot(records=()))
            screen._on_worker_state(event)
            await pilot.pause()

    async def test_technical_log_worker_handlers(self):
        controller = self._controller()
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 40)) as pilot:
            app.push_screen(TechnicalLogScreen(controller))
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, TechnicalLogScreen)
            worker = MagicMock()
            event = MagicMock()
            event.worker = worker
            screen._worker = worker
            event.state = WorkerState.ERROR
            screen._on_worker_state(event)
            content = str(screen.query_one("#tech-log-content").render())
            self.assertIn("unavailable", content)
            event.state = WorkerState.SUCCESS
            event.worker.result = None
            screen._on_worker_state(event)
            event.worker.result = (screen._load_token, None)
            screen._on_worker_state(event)
            event.worker.result = (
                "stale",
                TechnicalLogSnapshot(path=Path("/tmp/l"), lines=()),
            )
            screen._on_worker_state(event)
            await pilot.pause()

    async def test_controller_log_paths(self):
        controller = self._controller()
        self.assertTrue(str(controller.technical_log_path()))
        tail = controller.read_technical_log_tail(max_lines=5)
        self.assertIsNotNone(tail.path)
        controller.clear_operation_history()
