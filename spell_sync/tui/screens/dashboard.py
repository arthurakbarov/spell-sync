"""Main TUI dashboard."""

from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static
from textual.worker import WorkerState

from ...application.reports import DashboardSeverity
from ..controller import TuiController
from ..workers import LoadTokenMixin


def _display_path(path: str) -> str:
    home = str(Path.home())
    if path.startswith(home):
        return "~" + path[len(home) :]
    return path


class DashboardScreen(LoadTokenMixin, Screen[None]):
    BINDINGS = [
        ("r", "refresh_dashboard", "Refresh"),
        ("s", "open_status", "Status"),
        ("h", "open_health", "Health"),
    ]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller
        self._active_token = 0
        self._blocked = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="narrow-warning")
        yield Static(id="blocking-banner")
        yield Static(id="dashboard-summary")
        yield Static(id="dashboard-issues")
        with Vertical(id="action-grid"):
            yield Button("Review and update", id="btn-review-update", variant="primary")
            yield Button(
                "Review recovery",
                id="btn-recovery",
                disabled=True,
                classes="-disabled-action",
            )
            yield Static("Direct actions", classes="section-label")
            yield Button("Pull new words", id="btn-pull")
            yield Button("Push wordlist", id="btn-push")
            yield Static("Manage", classes="section-label")
            yield Button("Targets", id="btn-targets")
            yield Static("Support", classes="section-label")
            yield Button("Health", id="btn-health")
            yield Button("History", id="btn-history")
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
        self.query_one("#btn-review-update", Button).disabled = loading

    def _format_summary(self, state) -> str:
        snapshot = state.snapshot
        word_count = f"{snapshot.wordlist_count:,}"
        lines = [
            "Spell Sync",
            "",
            "Canonical wordlist",
            f"  {_display_path(state.wordlist_path)}",
            f"  {word_count} words",
            "",
            "Applications",
        ]
        if state.targets_ready:
            lines.append(f"  {state.targets_ready} ready")
        if state.targets_needs_attention:
            lines.append(f"  {state.targets_needs_attention} need attention")
        if state.targets_disabled:
            lines.append(f"  {state.targets_disabled} disabled")
        if state.targets_unavailable:
            lines.append(f"  {state.targets_unavailable} unavailable")
        if not any(
            (
                state.targets_ready,
                state.targets_needs_attention,
                state.targets_disabled,
                state.targets_unavailable,
            )
        ):
            lines.append("  No application targets configured")
        lines.extend(["", state.overall_label])
        if state.last_operation_summary:
            lines.append(state.last_operation_summary)
        return "\n".join(lines)

    def _render_dashboard(self, state) -> None:
        self.query_one("#dashboard-summary", Static).update(self._format_summary(state))
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
        recovery_needed = state.pending_recovery or any(
            issue.code in {"pending_recovery", "corrupt_journal"} for issue in state.issues
        )

        review_btn = self.query_one("#btn-review-update", Button)
        recovery_btn = self.query_one("#btn-recovery", Button)
        pull_btn = self.query_one("#btn-pull", Button)
        push_btn = self.query_one("#btn-push", Button)

        pull_btn.disabled = self._blocked
        push_btn.disabled = self._blocked

        if recovery_needed:
            review_btn.disabled = True
            review_btn.remove_class("primary")
            recovery_btn.disabled = False
            recovery_btn.remove_class("-disabled-action")
            recovery_btn.variant = "primary"
            recovery_btn.label = "Review recovery"
        else:
            review_btn.disabled = self._blocked
            review_btn.variant = "primary"
            recovery_btn.disabled = True
            recovery_btn.add_class("-disabled-action")
            recovery_btn.variant = "default"
            recovery_btn.label = "Review recovery"

        banner = self.query_one("#blocking-banner", Static)
        if state.pending_recovery:
            banner.update(
                "Recovery required\n"
                "An unfinished transaction must be reviewed before another write operation."
            )
        elif any(issue.code == "invalid_config" for issue in state.issues):
            issue = next(i for i in state.issues if i.code == "invalid_config")
            banner.update(f"Configuration blocked\n{issue.title}\n{issue.detail}")
        elif any(issue.code == "unreadable_wordlist" for issue in state.issues):
            issue = next(i for i in state.issues if i.code == "unreadable_wordlist")
            banner.update(f"Wordlist blocked\n{issue.title}\n{issue.detail}")
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
        if button_id == "btn-review-update":
            self.action_open_review_update()
        elif button_id == "btn-pull":
            self.action_open_pull()
        elif button_id == "btn-push":
            self.action_open_preview()
        elif button_id == "btn-health":
            self.action_open_health()
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
        elif button_id == "btn-history":
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

    def action_open_review_update(self) -> None:
        if self._blocked:
            self.notify("Writes are blocked. Resolve recovery or blocking issues first.")
            return
        from .review_update_screen import ReviewUpdateScreen

        self.app.push_screen(ReviewUpdateScreen())

    def action_open_preview(self) -> None:
        if self._blocked:
            self.notify("Writes are blocked. Resolve recovery or blocking issues first.")
            return
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

    def action_open_health(self) -> None:
        from .doctor_screen import DoctorScreen

        self.app.push_screen(DoctorScreen(self._controller))

    action_open_doctor = action_open_health
