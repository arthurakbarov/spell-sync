"""Operation history and technical log screens."""

from datetime import datetime

from textual import on, work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Select, Static
from textual.worker import Worker, WorkerState

from ...application.events import OperationKind
from ...application.product_concepts import dictionaries_updated_phrase
from ...application.reports import OperationOutcome
from ...diagnostics.history_record import OperationHistoryRecord
from ...diagnostics.technical_event_log import ParsedTechnicalLogEvent, parse_technical_log_line
from ..controller import TuiController
from ..layout import action_bar, loading_message, set_optional_static, sync_data_table_rows
from ..operational import OPERATIONAL_EXCEPTIONS
from ..workers import LoadTokenMixin, is_terminal_worker_state

_MAX_TECH_LOG_ROWS = 200
_MAX_FALLBACK_LINES = 40
_MAX_FALLBACK_LINE_LENGTH = 160


def _format_timestamp(value: datetime) -> str:
    local = value.astimezone()
    return local.strftime("%Y-%m-%d %H:%M")


def _history_detail(record: OperationHistoryRecord) -> str:
    if record.operation == "pull" and record.added_words:
        return f"{record.added_words} added"
    if record.operation == "push" and record.updated_targets:
        return dictionaries_updated_phrase(record.updated_targets)
    if record.operation == "setup" and record.created_files:
        return f"{record.created_files} files"
    if record.operation == "recover" and record.restored_files:
        return f"{record.restored_files} restored"
    return record.outcome.replace("_", " ").title()


def _technical_event_message(event: ParsedTechnicalLogEvent) -> str:
    parts = [event.operation.value]
    if event.stage is not None:
        parts.append(event.stage.value)
    if event.reason is not None:
        parts.append(event.reason.value)
    if event.outcome is not None:
        parts.append(event.outcome.value)
    if event.target_id is not None:
        parts.append(f"target={event.target_id.value}")
    if event.completed is not None and event.total is not None:
        parts.append(f"{event.completed}/{event.total}")
    return " · ".join(parts)


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
        with VerticalScroll(id="screen-body", classes="screen-body"):
            yield Static("Operation history", id="logs-title")
            yield Static(
                "Operation history stores counts and outcomes, not your words.",
                id="logs-privacy",
            )
            yield Select(
                [
                    ("All operations", "all"),
                    ("Setup", "setup"),
                    ("Collect my words", "pull"),
                    ("Update my apps", "push"),
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
            yield DataTable(id="history-table", cursor_type="row")
            yield action_bar(
                Button("Refresh", id="btn-refresh"),
                Button("Clear operation history", id="btn-clear"),
                Button("Back", id="btn-back"),
            )
        yield Footer()

    def on_mount(self) -> None:
        # Hide until load/render — empty status keeps margin above the table.
        set_optional_static(self.query_one("#logs-status", Static), "")
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
        table = self.query_one("#history-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Time", "Operation", "Outcome", "Details")
        for index, record in enumerate(self._records):
            detail = _history_detail(record)
            if record.warnings:
                detail = f"{detail} !"
            table.add_row(
                _format_timestamp(record.timestamp),
                record.operation.title(),
                record.outcome.replace("_", " ").title(),
                detail,
                key=str(index),
            )
        status = "\n".join(lines[2:4]) if len(lines) > 2 else ""
        set_optional_static(self.query_one("#logs-status", Static), status)
        sync_data_table_rows(table)
        # Nothing to clear when the table is empty.
        self.query_one("#btn-clear", Button).display = bool(self._records)

    def _start_load(self) -> None:
        if self.is_mounted:
            self.query_one("#history-table", DataTable).clear()
            set_optional_static(
                self.query_one("#logs-status", Static),
                loading_message("Loading operation history...", "history_load"),
            )
            sync_data_table_rows(self.query_one("#history-table", DataTable))
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
        except OPERATIONAL_EXCEPTIONS:
            return token, None
        return token, snapshot

    @on(Worker.StateChanged)
    def _on_worker_state(self, event: Worker.StateChanged) -> None:
        if event.worker != self._worker or not is_terminal_worker_state(event.state):
            return
        self.query_one("#btn-refresh", Button).disabled = False
        clear_btn = self.query_one("#btn-clear", Button)
        clear_btn.disabled = False
        if event.state is WorkerState.ERROR:
            set_optional_static(
                self.query_one("#logs-status", Static),
                "× History could not be loaded.",
            )
            sync_data_table_rows(self.query_one("#history-table", DataTable))
            clear_btn.display = False
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
            set_optional_static(
                self.query_one("#logs-status", Static),
                "× History could not be loaded.",
            )
            sync_data_table_rows(self.query_one("#history-table", DataTable))
            clear_btn.display = False
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

    @on(DataTable.RowSelected, "#history-table")
    def _on_history_row_selected(self, event: DataTable.RowSelected) -> None:
        raw_key = event.row_key.value
        if raw_key is None:
            return
        try:
            index = int(raw_key)
        except TypeError, ValueError:
            return
        if 0 <= index < len(self._records):
            self.app.push_screen(HistoryDetailsScreen(self._records[index]))


class HistoryDetailsScreen(Screen[None]):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, record: OperationHistoryRecord) -> None:
        super().__init__()
        self._record = record

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="screen-body", classes="screen-body"):
            yield Static(id="details-content")
            yield action_bar(Button("Back", id="btn-back"))
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
            if record.operation == "push":
                updated_label = "Dictionaries updated"
            elif record.operation == "targets":
                updated_label = "Apps changed"
            else:
                updated_label = "Updated"
            lines.extend(["", f"{updated_label}:\n  {record.updated_targets}"])
        if record.skipped_targets:
            skipped_label = "Dictionaries skipped" if record.operation == "push" else "Skipped"
            lines.extend(["", f"{skipped_label}:\n  {record.skipped_targets}"])
        if record.additions:
            lines.extend(["", f"Additions:\n  {record.additions}"])
        if record.removals:
            lines.extend(["", f"Removals:\n  {record.removals}"])
        if record.added_words:
            lines.extend(["", f"Words added:\n  {record.added_words}"])
        if record.created_files:
            lines.extend(["", f"Files created:\n  {record.created_files}"])
        if record.enabled_targets:
            lines.extend(["", f"Apps enabled:\n  {record.enabled_targets}"])
        if record.transaction_id:
            lines.extend(["", f"Record:\n  {record.transaction_id[:8]}..."])
        if record.setup_id:
            lines.extend(["", f"Setup:\n  {record.setup_id[:8]}..."])
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
        with VerticalScroll(id="screen-body", classes="screen-body"):
            yield Static(id="tech-log-summary")
            yield DataTable(id="tech-log-table")
            yield Static(id="tech-log-content")
            yield action_bar(
                Button("Refresh", id="btn-refresh"),
                Button("Back", id="btn-back"),
            )
        yield Footer()

    def on_mount(self) -> None:
        set_optional_static(self.query_one("#tech-log-content", Static), "")
        self._start_load()

    def _start_load(self) -> None:
        self._load_token = self._begin_load()
        self._worker = self._load_log_worker(self._load_token)

    @work(thread=True, exclusive=True)
    def _load_log_worker(self, token: int) -> tuple[int, object]:
        try:
            snapshot = self._controller.read_technical_log_tail()
        except OPERATIONAL_EXCEPTIONS:
            return token, None
        return token, snapshot

    @on(Worker.StateChanged)
    def _on_worker_state(self, event: Worker.StateChanged) -> None:
        if event.worker != self._worker or not is_terminal_worker_state(event.state):
            return
        if event.state is WorkerState.ERROR:
            set_optional_static(
                self.query_one("#tech-log-content", Static),
                "× Technical log unavailable.",
            )
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
            set_optional_static(
                self.query_one("#tech-log-content", Static),
                "× Technical log unavailable.",
            )
            return
        snapshot = payload
        summary_lines = [
            "Technical log",
            "",
            "Path:",
            f"  {snapshot.path}",
            "",
            "Showing the latest 200 lines.",
        ]
        if snapshot.truncated:
            summary_lines.append("Showing the most recent part of the log.")
        if snapshot.detail:
            summary_lines.append(snapshot.detail)
        self.query_one("#tech-log-summary", Static).update("\n".join(summary_lines))

        table = self.query_one("#tech-log-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Time", "Level", "Event", "Message")
        fallback: list[str] = []
        for line in snapshot.lines[-_MAX_TECH_LOG_ROWS:]:
            parsed = parse_technical_log_line(line)
            if parsed is None:
                fallback.append(line[:_MAX_FALLBACK_LINE_LENGTH])
                continue
            table.add_row(
                parsed.timestamp,
                parsed.severity.value,
                parsed.event_id.value,
                _technical_event_message(parsed),
            )
        sync_data_table_rows(table)
        fallback_static = self.query_one("#tech-log-content", Static)
        if fallback:
            # One newline after the label — a blank line looks like a layout gap.
            set_optional_static(
                fallback_static,
                "Unparsed log lines:\n" + "\n".join(fallback[-_MAX_FALLBACK_LINES:]),
            )
        elif not snapshot.lines:
            set_optional_static(fallback_static, "(empty)")
        else:
            set_optional_static(fallback_static, "")

    def action_back(self) -> None:
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_back()
        elif event.button.id == "btn-refresh":
            self._start_load()


class ClearHistoryConfirmScreen(Screen[None]):
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, controller: TuiController, logs_screen: LogsScreen) -> None:
        super().__init__()
        self._controller = controller
        self._logs_screen: LogsScreen = logs_screen

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="screen-body", classes="screen-body confirm-body"):
            yield Static(
                "\n".join(
                    [
                        "Clear operation history?",
                        "",
                        "This does not change your word list or app dictionaries.",
                    ]
                )
            )
            yield action_bar(
                Button("Clear", id="btn-confirm", variant="error"),
                Button("Cancel", id="btn-cancel"),
            )
        yield Footer()

    def action_cancel(self) -> None:
        self.app.pop_screen()

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
