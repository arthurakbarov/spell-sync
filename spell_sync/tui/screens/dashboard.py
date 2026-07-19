"""Main TUI dashboard."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static
from textual.worker import WorkerState

from ...application.reports import DashboardSeverity
from ..controller import TuiController
from ..workers import LoadTokenMixin


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
        self._blocked = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="narrow-warning")
        yield Static(id="recovery-banner")
        yield Static(id="dashboard-summary")
        yield Static(id="dashboard-issues")
        with Vertical(id="action-grid"):
            yield Button("Status", id="btn-status", variant="primary")
            yield Button("Preview", id="btn-preview")
            yield Button("Doctor", id="btn-doctor")
            yield Button("Pull", id="btn-pull")
            yield Button("Push", id="btn-push")
            yield Button("Targets", id="btn-targets")
            yield Button("Recovery", id="btn-recovery", disabled=True, classes="-disabled-action")
            yield Button("Logs", id="btn-logs")
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

        self._blocked = (
            state.pending_recovery
            or state.overall_severity is DashboardSeverity.BLOCKED
            or self._controller.mutation_active
        )
        self.query_one("#btn-pull", Button).disabled = self._blocked
        self.query_one("#btn-push", Button).disabled = self._blocked
        recovery_btn = self.query_one("#btn-recovery", Button)
        recovery_needed = state.pending_recovery or any(
            issue.code in {"pending_recovery", "corrupt_journal"} for issue in state.issues
        )
        if recovery_needed:
            recovery_btn.disabled = False
            recovery_btn.remove_class("-disabled-action")
            recovery_btn.label = "Recovery"
        else:
            recovery_btn.disabled = True
            recovery_btn.add_class("-disabled-action")
            recovery_btn.label = "Recovery"

        banner = self.query_one("#recovery-banner", Static)
        if state.pending_recovery:
            banner.update("! Recovery required — resolve the unfinished transaction before writes.")
        elif any(issue.code == "corrupt_journal" for issue in state.issues):
            banner.update("× Corrupt recovery journal — inspect Recovery before writes.")
        else:
            banner.update("")

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
        elif button_id == "btn-preview" or button_id == "btn-push":
            self.action_open_preview()
        elif button_id == "btn-doctor":
            self.action_open_doctor()
        elif button_id == "btn-pull":
            self.action_open_pull()
        elif button_id == "btn-quit":
            if self._controller.mutation_active:
                self.notify(
                    "The operation is in progress and must finish or roll back safely.",
                    severity="warning",
                )
                return
            self.app.exit(0)
        elif button_id == "btn-recovery":
            self.action_open_recovery()
        elif button_id == "btn-logs":
            from .logs_screen import LogsScreen

            self.app.push_screen(LogsScreen(self._controller))
        elif button_id == "btn-targets":
            self.action_open_targets()

    def action_open_targets(self) -> None:
        from .target_settings_screen import TargetSettingsScreen

        self.app.push_screen(TargetSettingsScreen(self._controller))

    def action_refresh_dashboard(self) -> None:
        self._refresh_layout_warning()
        self.refresh_dashboard()

    def action_open_status(self) -> None:
        from .status_screen import StatusScreen

        self.app.push_screen(StatusScreen(self._controller))

    def action_open_preview(self) -> None:
        from .preview_screen import PreviewScreen

        self.app.push_screen(PreviewScreen(self._controller))

    def action_open_pull(self) -> None:
        if self._blocked:
            self.notify("Writes are blocked. Resolve recovery or blocking issues first.")
            return
        from .pull_screen import PullScreen

        self.app.push_screen(PullScreen(self._controller))

    def action_open_recovery(self) -> None:
        from .recovery_screen import RecoveryScreen

        self.app.push_screen(RecoveryScreen(self._controller))

    def action_open_doctor(self) -> None:
        from .doctor_screen import DoctorScreen

        self.app.push_screen(DoctorScreen(self._controller))
