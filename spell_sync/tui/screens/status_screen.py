"""Read-only status view."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static
from textual.worker import WorkerState

from ...application.reports import StatusDetailSnapshot
from ..controller import TuiController
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
        yield Static(id="status-content")
        yield Button("Refresh", id="btn-refresh", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        try:
            self._render_snapshot(self._controller.status_detail())
        except Exception:
            self.query_one("#status-content", Static).update("× Status load failed.")

    def _set_loading(self, loading: bool) -> None:
        self.query_one("#btn-refresh", Button).disabled = loading

    def _render_snapshot(self, snapshot: StatusDetailSnapshot) -> None:
        self._snapshot = snapshot
        lines = [
            "Status",
            f"Wordlist: {snapshot.wordlist_path}",
            f"Project: {snapshot.project_dir}",
            "",
            "Configuration paths:",
        ]
        if snapshot.config_paths:
            lines.extend(f"  {path}" for path in snapshot.config_paths)
        else:
            lines.append("  (none)")
        lines.append("")
        if snapshot.load_error:
            lines.append(f"× {snapshot.load_error}")
        elif snapshot.wordlist_error is not None:
            lines.append(f"× Wordlist error (exit {int(snapshot.wordlist_error)})")
        else:
            lines.append(f"Words in wordlist: {snapshot.wordlist_count}")
            if snapshot.destructive_risk:
                lines.append(f"! {snapshot.destructive_risk}")
        lines.append("")
        lines.append("Targets:")
        if not snapshot.targets:
            lines.append("  – No targets configured.")
        for target in snapshot.targets:
            enabled = "enabled" if target.enabled else "disabled"
            availability = "available" if target.available else "unavailable"
            lines.append(
                f"  {target.name}: {enabled}, {availability}, "
                f"read={target.read_status}, format={target.format or 'n/a'}"
            )
            if target.path:
                lines.append(f"    path: {target.path}")
            if target.word_count is not None:
                lines.append(f"    words: {target.word_count}")
            if target.detail:
                lines.append(f"    detail: {target.detail}")
        if snapshot.skipped_unreadable:
            lines.append("")
            lines.append(f"Skipped unreadable: {', '.join(snapshot.skipped_unreadable)}")
        if snapshot.skipped_corrupt:
            lines.append(f"Skipped corrupt: {', '.join(snapshot.skipped_corrupt)}")
        self.query_one("#status-content", Static).update("\n".join(lines))

    def refresh_status(self) -> None:
        self._active_token = self._begin_load()
        self._set_loading(True)
        self.query_one("#status-content", Static).update("Loading status...")
        self.load_status_worker()

    @work(thread=True, exclusive=True, group="status-load")
    def load_status_worker(self) -> StatusDetailSnapshot:
        try:
            return self._controller.status_detail()
        except Exception:
            return StatusDetailSnapshot(
                wordlist_path="",
                project_dir="",
                config_paths=(),
                wordlist_count=0,
                targets=(),
                skipped_unreadable=(),
                skipped_corrupt=(),
                load_error="Status could not be loaded.",
            )

    def on_load_status_worker_state_changed(self, event) -> None:
        if event.state is WorkerState.RUNNING:
            return
        self._set_loading(False)
        if event.state is WorkerState.ERROR:
            if self.is_mounted:
                self.query_one("#status-content", Static).update(
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

    def action_refresh_status(self) -> None:
        self.refresh_status()

    def action_back(self) -> None:
        self.app.pop_screen()
