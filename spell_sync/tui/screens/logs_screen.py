"""Operation history and technical log screens."""

from __future__ import annotations

from datetime import datetime

from textual import on, work
from textual.app import ComposeResult
from textual.containers import ScrollableContainer
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Select, Static
from textual.worker import Worker, WorkerState

from ...application.events import OperationKind
from ...application.reports import OperationOutcome
from ...diagnostics.history_record import OperationHistoryRecord
from ..controller import TuiController
from ..workers import LoadTokenMixin


def _format_timestamp(value: datetime) -> str:
    local = value.astimezone()
    return local.strftime("%Y-%m-%d %H:%M")


def _summary_line(record: OperationHistoryRecord) -> str:
    marker = " !" if record.warnings else ""
    if record.operation == "pull" and record.added_words:
        detail = f"{record.added_words} added"
    elif record.operation == "push" and record.updated_targets:
        detail = f"{record.updated_targets} updated"
    elif record.operation == "setup" and record.created_files:
        detail = f"{record.created_files} files"
    elif record.operation == "recover" and record.restored_files:
        detail = f"{record.restored_files} restored"
    else:
        detail = record.outcome.replace("_", " ").title()
    return (
        f"{_format_timestamp(record.timestamp)}  "
        f"{record.operation.title():<8}  "
        f"{record.outcome.replace('_', ' ').title():<18}  "
        f"{detail}{marker}"
    )


class LogsScreen(LoadTokenMixin, Screen[None]):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller
        self._records: tuple[OperationHistoryRecord, ...] = ()
        self._malformed = 0
        self._load_token = 0
        self._worker: Worker | None = None
        self._operation_filter: OperationKind | None = None
        self._outcome_filter: OperationOutcome | None = None
        self._filters_ready = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Operation history", id="logs-title")
        yield Select(
            [
                ("All operations", "all"),
                ("Setup", "setup"),
                ("Pull", "pull"),
                ("Push", "push"),
                ("Recovery", "recover"),
            ],
            id="filter-operation",
            value="all",
        )
        yield Select(
            [
                ("All outcomes", "all"),
                ("Completed", "completed"),
                ("Warnings", "completed_with_warnings"),
                ("Stopped safely", "stopped_safely"),
                ("Failed / recovery required", "failed"),
            ],
            id="filter-outcome",
            value="all",
        )
        yield Static(id="logs-status")
        yield ScrollableContainer(id="history-list")
        yield Button("Refresh", id="btn-refresh")
        yield Button("Clear operation history", id="btn-clear")
        yield Button("Technical log", id="btn-tech-log")
        yield Button("Back", id="btn-back")
        yield Footer()

    def on_mount(self) -> None:
        self.call_after_refresh(self._start_load)

    def _filters_enabled(self) -> None:
        self._filters_ready = True

    def _render_history(self) -> None:
        lines = ["Operation history", ""]
        if self._malformed:
            lines.append(f"! Skipped {self._malformed} malformed history line(s).")
            lines.append("")
        if not self._records:
            lines.append("No completed operations recorded yet.")
        container = self.query_one("#history-list", ScrollableContainer)
        container.remove_children()
        for index, record in enumerate(self._records):
            line = _summary_line(record)
            container.mount(Button(line, id=f"history-row-{index}", classes="history-row"))
        status = "\n".join(lines[2:4]) if len(lines) > 2 else ""
        self.query_one("#logs-status", Static).update(status)

    def _start_load(self) -> None:
        if self.is_mounted:
            self.query_one("#history-list", ScrollableContainer).remove_children()
        self._load_token = self._begin_load()
        self.query_one("#btn-refresh", Button).disabled = True
        self.query_one("#btn-clear", Button).disabled = True
        self._worker = self._load_history_worker(self._load_token)

    @work(thread=True, exclusive=True)
    def _load_history_worker(self, token: int) -> tuple[int, object]:
        try:
            snapshot = self._controller.load_operation_history(
                limit=50,
                operation=self._operation_filter,
                outcome=self._outcome_filter,
            )
        except Exception:
            return token, None
        return token, snapshot

    @on(Worker.StateChanged)
    def _on_worker_state(self, event: Worker.StateChanged) -> None:
        if event.worker != self._worker or event.state is WorkerState.RUNNING:
            return
        self.query_one("#btn-refresh", Button).disabled = False
        self.query_one("#btn-clear", Button).disabled = False
        if event.state is WorkerState.ERROR:
            self.query_one("#logs-status", Static).update("× History could not be loaded.")
            return
        if event.state is not WorkerState.SUCCESS:
            return
        result = event.worker.result
        if result is None:
            return
        token, payload = result
        if not isinstance(token, int) or not self._is_current_load(token):
            return
        from ...diagnostics.types import OperationHistorySnapshot

        if not isinstance(payload, OperationHistorySnapshot):
            self.query_one("#logs-status", Static).update("× History could not be loaded.")
            return
        snapshot = payload
        self._records = snapshot.records
        self._malformed = snapshot.malformed_lines
        if self.is_mounted:
            self._render_history()
        self._filters_enabled()

    def action_back(self) -> None:
        self.app.pop_screen()

    @on(Select.Changed, "#filter-operation")
    def _on_operation_filter(self, event: Select.Changed) -> None:
        if not self._filters_ready:
            return
        mapping = {
            "all": None,
            "setup": OperationKind.SETUP,
            "pull": OperationKind.PULL,
            "push": OperationKind.PUSH,
            "recover": OperationKind.RECOVER,
        }
        selected = mapping.get(str(event.value))
        if selected == self._operation_filter:
            return
        self._operation_filter = selected
        self._start_load()

    @on(Select.Changed, "#filter-outcome")
    def _on_outcome_filter(self, event: Select.Changed) -> None:
        if not self._filters_ready:
            return
        mapping = {
            "all": None,
            "completed": OperationOutcome.COMPLETED,
            "completed_with_warnings": OperationOutcome.COMPLETED_WITH_WARNINGS,
            "stopped_safely": OperationOutcome.STOPPED_SAFELY,
            "failed": OperationOutcome.FAILED,
        }
        selected = mapping.get(str(event.value))
        if selected == self._outcome_filter:
            return
        self._outcome_filter = selected
        self._start_load()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_back()
            return
        if event.button.id == "btn-refresh":
            self._start_load()
            return
        if event.button.id == "btn-clear":
            self.app.push_screen(ClearHistoryConfirmScreen(self._controller, self))
            return
        if event.button.id == "btn-tech-log":
            self.app.push_screen(TechnicalLogScreen(self._controller))
            return
        if event.button.id and event.button.id.startswith("history-row-"):
            index = int(event.button.id.rsplit("-", 1)[-1])
            if 0 <= index < len(self._records):
                self.app.push_screen(HistoryDetailsScreen(self._records[index]))


class HistoryDetailsScreen(Screen[None]):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, record: OperationHistoryRecord) -> None:
        super().__init__()
        self._record = record

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="details-content")
        yield Button("Back", id="btn-back")
        yield Footer()

    def on_mount(self) -> None:
        record = self._record
        lines = [
            f"{record.operation.title()} · {record.outcome.replace('_', ' ').title()}",
            "",
            f"Started:\n  {_format_timestamp(record.timestamp)}",
            "",
            f"Duration:\n  {record.duration_ms} ms",
        ]
        if record.updated_targets:
            lines.extend(["", f"Targets updated:\n  {record.updated_targets}"])
        if record.skipped_targets:
            lines.extend(["", f"Targets skipped:\n  {record.skipped_targets}"])
        if record.additions:
            lines.extend(["", f"Additions:\n  {record.additions}"])
        if record.removals:
            lines.extend(["", f"Removals:\n  {record.removals}"])
        if record.added_words:
            lines.extend(["", f"Words added:\n  {record.added_words}"])
        if record.created_files:
            lines.extend(["", f"Files created:\n  {record.created_files}"])
        if record.enabled_targets:
            lines.extend(["", f"Enabled targets:\n  {record.enabled_targets}"])
        if record.transaction_id:
            lines.extend(["", f"Transaction:\n  {record.transaction_id[:8]}…"])
        if record.setup_id:
            lines.extend(["", f"Setup:\n  {record.setup_id[:8]}…"])
        if record.warnings:
            lines.extend(["", f"Warnings:\n  {record.warnings}"])
        self.query_one("#details-content", Static).update("\n".join(lines))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()


class TechnicalLogScreen(LoadTokenMixin, Screen[None]):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller
        self._load_token = 0
        self._worker: Worker | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="tech-log-content")
        yield Button("Refresh", id="btn-refresh")
        yield Button("Back", id="btn-back")
        yield Footer()

    def on_mount(self) -> None:
        self._start_load()

    def _start_load(self) -> None:
        self._load_token = self._begin_load()
        self._worker = self._load_log_worker(self._load_token)

    @work(thread=True, exclusive=True)
    def _load_log_worker(self, token: int) -> tuple[int, object]:
        try:
            snapshot = self._controller.read_technical_log_tail()
        except Exception:
            return token, None
        return token, snapshot

    @on(Worker.StateChanged)
    def _on_worker_state(self, event: Worker.StateChanged) -> None:
        if event.worker != self._worker or event.state is WorkerState.RUNNING:
            return
        if event.state is WorkerState.ERROR:
            self.query_one("#tech-log-content", Static).update("× Technical log unavailable.")
            return
        if event.state is not WorkerState.SUCCESS:
            return
        result = event.worker.result
        if result is None:
            return
        token, payload = result
        if not isinstance(token, int) or not self._is_current_load(token):
            return
        from ...diagnostics.types import TechnicalLogSnapshot

        if not isinstance(payload, TechnicalLogSnapshot):
            self.query_one("#tech-log-content", Static).update("× Technical log unavailable.")
            return
        snapshot = payload
        lines = [
            "Technical log",
            "",
            "Path:",
            f"  {snapshot.path}",
            "",
            "Showing the latest 200 lines.",
        ]
        if snapshot.truncated:
            lines.append("Showing the most recent part of the log.")
        if snapshot.detail:
            lines.append(snapshot.detail)
        lines.append("")
        lines.extend(snapshot.lines or ["(empty)"])
        self.query_one("#tech-log-content", Static).update("\n".join(lines))

    def action_back(self) -> None:
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_back()
        elif event.button.id == "btn-refresh":
            self._start_load()


class ClearHistoryConfirmScreen(Screen[None]):
    def __init__(self, controller: TuiController, logs_screen: LogsScreen) -> None:
        super().__init__()
        self._controller = controller
        self._logs_screen: LogsScreen = logs_screen

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "\n".join(
                [
                    "Clear operation history?",
                    "",
                    "This does not change your wordlist or application dictionaries.",
                ]
            )
        )
        yield Button("Clear", id="btn-confirm", variant="error")
        yield Button("Cancel", id="btn-cancel")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.app.pop_screen()
            return
        if event.button.id == "btn-confirm":
            result = self._controller.clear_operation_history()
            if not result.ok:
                self.notify(result.detail or "History could not be cleared.", severity="error")
            else:
                self.notify("Operation history cleared.")
            self.app.pop_screen()
            self._logs_screen._start_load()
