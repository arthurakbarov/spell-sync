"""Read-only status view."""

from textual import work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Static
from textual.worker import WorkerState

from ...application.product_concepts import DICTIONARY_TABLE_COLUMN
from ...application.reports import StatusDetailSnapshot
from ...application.status_copy import format_status_summary
from ..controller import TuiController
from ..layout import action_bar, loading_message, sync_data_table_rows
from ..operational import OPERATIONAL_EXCEPTIONS
from ..workers import LoadTokenMixin


class StatusScreen(LoadTokenMixin, Screen[None]):
    BINDINGS = [
        ("escape", "back", "Back"),
        ("r", "refresh_status", "Refresh"),
    ]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller
        self._snapshot: StatusDetailSnapshot | None = None
        self._active_token = 0

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="screen-body", classes="screen-body"):
            yield Static(id="status-summary", classes="screen-prose")
            yield DataTable(id="status-table")
            yield action_bar(
                Button("Refresh", id="btn-refresh"),
                Button("Back", id="btn-back"),
            )
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#status-table", DataTable)
        table.cursor_type = "row"
        table.add_columns(
            DICTIONARY_TABLE_COLUMN, "Enabled", "Available", "Read", "Words", "Format"
        )
        try:
            self._render_snapshot(self._controller.status_detail())
        except OPERATIONAL_EXCEPTIONS:
            self.query_one("#status-summary", Static).update("× Status load failed.")
            table = self.query_one("#status-table", DataTable)
            table.clear()
            sync_data_table_rows(table)

    def _set_loading(self, loading: bool) -> None:
        self.query_one("#btn-refresh", Button).disabled = loading

    def _render_snapshot(self, snapshot: StatusDetailSnapshot) -> None:
        self._snapshot = snapshot
        summary = format_status_summary(snapshot)
        table = self.query_one("#status-table", DataTable)
        table.clear()
        self.query_one("#status-summary", Static).update(summary)
        if not snapshot.targets:
            table.add_row("(none)", "-", "-", "-", "-", "-")
            sync_data_table_rows(table)
            return
        for target in snapshot.targets:
            enabled = "✓ Yes" if target.enabled else "· No"
            available = "✓ Yes" if target.available else "× No"
            read_status = (target.read_status or "").strip()
            label = read_status[:1].upper() + read_status[1:] if read_status else "-"
            if read_status in {"ok", "ready", "readable"}:
                read_status = f"✓ {label}"
            elif read_status in {"error", "unreadable", "corrupt", "failed"}:
                read_status = f"× {label}"
            elif read_status and read_status not in {"-", "n/a"}:
                read_status = f"! {label}"
            else:
                read_status = label
            table.add_row(
                target.name,
                enabled,
                available,
                read_status,
                "-" if target.word_count is None else str(target.word_count),
                target.format or "n/a",
            )
        sync_data_table_rows(table)

    def refresh_status(self) -> None:
        self._active_token = self._begin_load()
        self._set_loading(True)
        self.query_one("#status-summary", Static).update(
            loading_message("Loading status...", "status")
        )
        self.load_status_worker()

    @work(thread=True, exclusive=True, group="status-load")
    def load_status_worker(self) -> StatusDetailSnapshot:
        try:
            return self._controller.status_detail()
        except OPERATIONAL_EXCEPTIONS:
            return StatusDetailSnapshot.unavailable()

    def on_load_status_worker_state_changed(self, event) -> None:
        if event.state is WorkerState.RUNNING:
            return
        self._set_loading(False)
        if event.state is WorkerState.ERROR:
            if self.is_mounted:
                self.query_one("#status-summary", Static).update(
                    "× Status unavailable — try Refresh."
                )
            return
        if event.state is not WorkerState.SUCCESS:
            return
        if not self._is_current_load(self._active_token):
            return
        self._render_snapshot(event.worker.result)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-refresh":
            self.action_refresh_status()
        elif event.button.id == "btn-back":
            self.action_back()

    def action_refresh_status(self) -> None:
        self.refresh_status()

    def action_back(self) -> None:
        self.app.pop_screen()
