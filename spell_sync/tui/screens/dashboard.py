"""Main TUI dashboard."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static
from textual.worker import WorkerState

from ..controller import TuiController
from ..workers import LoadTokenMixin

_DISABLED_HINT = "Available in Phase 4"


class DashboardScreen(LoadTokenMixin, Screen[None]):
    BINDINGS = [
        ("r", "refresh_dashboard", "Refresh"),
        ("p", "open_preview", "Preview"),
        ("s", "open_status", "Status"),
        ("d", "open_doctor", "Doctor"),
    ]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller
        self._active_token = 0

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="narrow-warning")
        yield Static(id="dashboard-summary")
        yield Static(id="dashboard-issues")
        with Vertical(id="action-grid"):
            yield Button("Status", id="btn-status", variant="primary")
            yield Button("Preview", id="btn-preview")
            yield Button("Doctor", id="btn-doctor")
            yield Button("Pull", id="btn-pull", disabled=True, classes="-disabled-action")
            yield Button("Push", id="btn-push", disabled=True, classes="-disabled-action")
            yield Button("Recovery", id="btn-recovery", disabled=True, classes="-disabled-action")
            yield Button("Logs", id="btn-logs", disabled=True, classes="-disabled-action")
            yield Button("Quit", id="btn-quit", variant="error")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_layout_warning()
        try:
            self._render_dashboard(self._controller.dashboard())
        except Exception:
            self.query_one("#dashboard-summary", Static).update("× Dashboard load failed.")

    def _refresh_layout_warning(self) -> None:
        warning = self.query_one("#narrow-warning", Static)
        if self.app.size.width < 80 or self.app.size.height < 24:
            warning.update("! Warning: terminal is smaller than 80x24 — layout may be cramped.")
        else:
            warning.update("")

    def _set_loading(self, loading: bool) -> None:
        self.query_one("#btn-status", Button).disabled = loading

    def _render_dashboard(self, state) -> None:
        snapshot = state.snapshot
        config_label = "✓ Valid" if state.config_valid else "× Invalid"
        recovery_label = "Yes" if state.pending_recovery else "No"
        lines = [
            "Spell Sync",
            f"Wordlist: {state.wordlist_path}",
            f"Configuration: {config_label} ({state.config_status})",
            f"Targets detected: {state.targets_detected}",
            f"Targets enabled: {state.targets_enabled}",
            f"Targets available: {state.targets_available}",
            f"Words in wordlist: {snapshot.wordlist_count}",
            f"Pending recovery: {recovery_label}",
            f"Overall status: {state.overall_label}",
        ]
        self.query_one("#dashboard-summary", Static).update("\n".join(lines))
        if state.issues:
            issue_lines = ["Issues:"]
            for issue in state.issues:
                prefix = {
                    "blocked": "×",
                    "warning": "!",
                    "ready": "✓",
                }[issue.severity.value]
                issue_lines.append(f"  {prefix} {issue.title}: {issue.detail}")
            self.query_one("#dashboard-issues", Static).update("\n".join(issue_lines))
        else:
            self.query_one("#dashboard-issues", Static).update("")

    def refresh_dashboard(self) -> None:
        self._active_token = self._begin_load()
        self._set_loading(True)
        self.query_one("#dashboard-summary", Static).update("Loading dashboard...")
        self.load_dashboard_worker()

    @work(thread=True, exclusive=True, group="dashboard-load")
    def load_dashboard_worker(self):
        try:
            return self._controller.dashboard()
        except Exception:
            return None

    def on_load_dashboard_worker_state_changed(self, event) -> None:
        if event.state is WorkerState.RUNNING:
            return
        self._set_loading(False)
        if event.state is WorkerState.ERROR:
            if self._is_current_load(self._active_token):
                self.query_one("#dashboard-summary", Static).update(
                    "× Dashboard unavailable — try Refresh."
                )
            return
        if event.state is not WorkerState.SUCCESS:
            return
        if not self._is_current_load(self._active_token):
            return
        payload = event.worker.result
        if payload is None:
            self.query_one("#dashboard-summary", Static).update("× Dashboard load failed.")
            return
        self._render_dashboard(payload)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "btn-status":
            self.action_open_status()
        elif button_id == "btn-preview":
            self.action_open_preview()
        elif button_id == "btn-doctor":
            self.action_open_doctor()
        elif button_id == "btn-quit":
            self.app.exit(0)
        elif button_id in {"btn-pull", "btn-push", "btn-recovery", "btn-logs"}:
            self.notify(_DISABLED_HINT, severity="warning")

    def action_refresh_dashboard(self) -> None:
        self._refresh_layout_warning()
        self.refresh_dashboard()

    def action_open_status(self) -> None:
        from .status_screen import StatusScreen

        self.app.push_screen(StatusScreen(self._controller))

    def action_open_preview(self) -> None:
        from .preview_screen import PreviewScreen

        self.app.push_screen(PreviewScreen(self._controller))

    def action_open_doctor(self) -> None:
        from .doctor_screen import DoctorScreen

        self.app.push_screen(DoctorScreen(self._controller))
