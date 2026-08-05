"""Main TUI dashboard."""

from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static
from textual.worker import WorkerState

from ...application.product_concepts import (
    CHECK_APPS_LABEL,
    COLLECT_WORDS_TECHNICAL,
    DASHBOARD_WORDLIST_LABEL,
    DASHBOARD_WORDLIST_SUBTITLE,
    REVIEW_AND_UPDATE_LABEL,
    UPDATE_APPS_TECHNICAL,
)
from ...application.reports import DashboardSeverity
from ...application.user_notices import (
    NoticeSeverity,
    build_notice,
    dashboard_issue_to_notice,
    format_notice_block,
    format_notice_details,
    format_notice_summary,
)
from ..controller import TuiController
from ..layout import loading_message, section_label
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
        with VerticalScroll(id="screen-body", classes="screen-body"):
            yield Static(id="narrow-warning")
            yield Static(id="blocking-banner")
            yield Static(id="dashboard-summary", classes="screen-prose")
            yield Static(id="dashboard-issues", classes="screen-prose")
            with Vertical(id="screen-actions", classes="dashboard-menu"):
                yield section_label("Usual path")
                yield Button(
                    REVIEW_AND_UPDATE_LABEL,
                    id="btn-review-update",
                    variant="primary",
                )
                yield section_label("Single steps")
                yield Button(COLLECT_WORDS_TECHNICAL, id="btn-pull")
                yield Button(UPDATE_APPS_TECHNICAL, id="btn-push")
                yield Button(CHECK_APPS_LABEL, id="btn-status")
                yield Button(
                    "Review recovery",
                    id="btn-recovery",
                    disabled=True,
                    classes="-disabled-action",
                )
                yield section_label("Manage")
                yield Button("Targets", id="btn-targets")
                yield Button("Change word list location", id="btn-change-wordlist")
                yield Static(
                    "Points Spell Sync at another wordlist.txt; does not move files.",
                    id="change-wordlist-hint",
                )
                yield section_label("Support")
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
            DASHBOARD_WORDLIST_LABEL,
            f"  {DASHBOARD_WORDLIST_SUBTITLE}",
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
                notice = dashboard_issue_to_notice(issue)
                prefix = {
                    "blocked": "×",
                    "warning": "!",
                    "ready": "✓",
                    "info": "→",
                }[notice.severity.value]
                issue_lines.append(f"  {prefix} {format_notice_summary(notice)}")
                issue_lines.append(f"     {format_notice_details(notice)}")
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
            review_btn.variant = "default"
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
            matching = [issue for issue in state.issues if issue.code == "pending_recovery"]
            if matching:
                notice = dashboard_issue_to_notice(matching[0])
            else:
                notice = build_notice("pending_recovery", severity=NoticeSeverity.BLOCKED)
            banner.update(format_notice_block(notice))
        elif any(issue.code == "invalid_config" for issue in state.issues):
            issue = next(i for i in state.issues if i.code == "invalid_config")
            banner.update(format_notice_block(dashboard_issue_to_notice(issue)))
        elif any(issue.code == "unreadable_wordlist" for issue in state.issues):
            issue = next(i for i in state.issues if i.code == "unreadable_wordlist")
            banner.update(format_notice_block(dashboard_issue_to_notice(issue)))
        elif any(issue.code == "corrupt_journal" for issue in state.issues):
            issue = next(i for i in state.issues if i.code == "corrupt_journal")
            banner.update(format_notice_block(dashboard_issue_to_notice(issue)))
        else:
            banner.update("")

    def refresh_dashboard(self) -> None:
        self._active_token = self._begin_load()
        self._set_loading(True)
        self.query_one("#dashboard-summary", Static).update(
            loading_message("Loading dashboard...", "dashboard")
        )
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
        elif button_id == "btn-status":
            self.action_open_status()
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
        elif button_id == "btn-change-wordlist":
            self.action_change_wordlist()

    def action_open_targets(self) -> None:
        from .target_settings_screen import TargetSettingsScreen

        self.app.push_screen(TargetSettingsScreen(self._controller))

    def action_change_wordlist(self) -> None:
        from .setup_welcome_screen import ChangeWordlistScreen

        self.app.push_screen(ChangeWordlistScreen(self._controller))

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
        from .review_update_screen import ReviewStartScreen

        self.app.push_screen(ReviewStartScreen(self._controller))

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

    def on_resize(self) -> None:
        self._refresh_layout_warning()
