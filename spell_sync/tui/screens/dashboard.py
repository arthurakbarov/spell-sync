"""Main TUI dashboard."""

from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static
from textual.worker import WorkerState

from ...application.product_concepts import (
    APPLICATIONS_LABEL,
    CHANGE_WORDLIST_HINT,
    CHECK_APPS_HELP,
    CHECK_APPS_LABEL,
    COLLECT_WORDS_HELP,
    COLLECT_WORDS_LABEL,
    DASHBOARD_EMPTY_APPS_CTA,
    DASHBOARD_NEXT_STEP,
    DASHBOARD_NO_APPS_LINE,
    DASHBOARD_WORDLIST_LABEL,
    HEALTH_BUTTON_HELP,
    NARROW_TERMINAL_HINT,
    REVIEW_AND_UPDATE_HELP,
    REVIEW_AND_UPDATE_LABEL,
    UPDATE_APPS_HELP,
    UPDATE_APPS_LABEL,
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
from ..layout import loading_message, menu_item, section_label
from ..operational import OPERATIONAL_EXCEPTIONS
from ..workers import LoadTokenMixin


def _display_path(path: str) -> str:
    home = str(Path.home())
    if path.startswith(home):
        return "~" + path[len(home) :]
    return path


def _apps_configured(state) -> bool:
    return bool(
        state.targets_ready
        or state.targets_needs_attention
        or state.targets_disabled
        or state.targets_unavailable
    )


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
            yield Static(id="dashboard-next-step", classes="screen-prose")
            yield Static(id="dashboard-summary", classes="screen-prose")
            yield Static(id="dashboard-issues", classes="screen-prose")
            with Vertical(id="screen-actions", classes="dashboard-menu"):
                yield section_label("Usual path")
                yield menu_item(
                    Button(
                        REVIEW_AND_UPDATE_LABEL,
                        id="btn-review-update",
                        variant="primary",
                    ),
                    REVIEW_AND_UPDATE_HELP,
                    hint_id="review-update-hint",
                )
                yield menu_item(
                    Button(
                        "Finish interrupted update",
                        id="btn-recovery",
                        disabled=True,
                    ),
                    item_id="recovery-menu-item",
                    visible=False,
                )
                yield section_label("Single steps")
                yield menu_item(
                    Button(COLLECT_WORDS_LABEL, id="btn-pull"),
                    COLLECT_WORDS_HELP,
                    hint_id="pull-hint",
                )
                yield menu_item(
                    Button(UPDATE_APPS_LABEL, id="btn-push"),
                    UPDATE_APPS_HELP,
                    hint_id="push-hint",
                )
                yield menu_item(
                    Button(CHECK_APPS_LABEL, id="btn-status"),
                    CHECK_APPS_HELP,
                    hint_id="status-hint",
                )
                yield section_label("Manage")
                yield menu_item(
                    Button(APPLICATIONS_LABEL, id="btn-targets"),
                    "Choose which apps Spell Sync updates.",
                    hint_id="targets-hint",
                )
                yield menu_item(
                    Button("Change word list location", id="btn-change-wordlist"),
                    CHANGE_WORDLIST_HINT,
                    hint_id="change-wordlist-hint",
                )
                yield section_label("Support")
                yield menu_item(
                    Button("Health", id="btn-health"),
                    HEALTH_BUTTON_HELP,
                    hint_id="health-hint",
                )
                yield menu_item(
                    Button("History", id="btn-history"),
                    "Past Collect, Update, and recovery runs.",
                    hint_id="history-hint",
                )
                # Exit is not Support — leave the app, not diagnose it.
                yield section_label("Exit")
                yield menu_item(Button("Quit", id="btn-quit", variant="error"))
        yield Footer()

    def _set_optional_static(self, widget_id: str, text: str) -> None:
        """Update a prose slot; hide it when empty so margin does not leave blank rows."""
        widget = self.query_one(widget_id, Static)
        content = text.strip()
        widget.update(content)
        widget.display = bool(content)

    def _set_recovery_item_visible(self, visible: bool) -> None:
        """Show/hide the whole recovery menu row (not only the button)."""
        self.query_one("#recovery-menu-item").display = visible
        self.query_one("#btn-recovery", Button).display = visible

    def on_mount(self) -> None:
        self._refresh_layout_warning()
        self._refresh_next_step()
        try:
            self._render_dashboard(self._controller.dashboard())
        except OPERATIONAL_EXCEPTIONS:
            self._render_load_failure("× Dashboard load failed.")

    def _render_load_failure(self, message: str) -> None:
        # Fail closed: unknown recovery/config state must not leave write gates open.
        self._blocked = True
        self.query_one("#dashboard-summary", Static).update(message)
        for button_id in ("#btn-review-update", "#btn-pull", "#btn-push"):
            self.query_one(button_id, Button).disabled = True
        self._set_recovery_item_visible(True)
        recovery_btn = self.query_one("#btn-recovery", Button)
        recovery_btn.disabled = False
        recovery_btn.variant = "primary"
        recovery_btn.label = "Finish interrupted update"
        self._set_optional_static("#dashboard-next-step", "")

    def _refresh_next_step(self, *, apps_configured: bool | None = None) -> None:
        if apps_configured is False:
            self._set_optional_static("#dashboard-next-step", DASHBOARD_EMPTY_APPS_CTA)
            return
        if self._controller.show_first_run_next_step:
            self._set_optional_static("#dashboard-next-step", DASHBOARD_NEXT_STEP)
        else:
            self._set_optional_static("#dashboard-next-step", "")

    def _refresh_layout_warning(self) -> None:
        narrow = self.app.size.width < 80 or self.app.size.height < 24
        if narrow:
            self._set_optional_static("#narrow-warning", f"! {NARROW_TERMINAL_HINT}")
        else:
            self._set_optional_static("#narrow-warning", "")
        # Compact mode: hide secondary hints to free vertical space.
        for widget_id in (
            "review-update-hint",
            "pull-hint",
            "push-hint",
            "status-hint",
            "targets-hint",
            "change-wordlist-hint",
            "health-hint",
            "history-hint",
        ):
            try:
                self.query_one(f"#{widget_id}", Static).display = not narrow
            except OPERATIONAL_EXCEPTIONS:
                continue

    def _set_loading(self, loading: bool) -> None:
        self.query_one("#btn-review-update", Button).disabled = loading

    def _format_summary(self, state) -> str:
        snapshot = state.snapshot
        word_count = f"{snapshot.wordlist_count:,}"
        # Same outline for every group: heading, then indented facts.
        indent = "    "
        lines = [
            DASHBOARD_WORDLIST_LABEL,
            f"{indent}{_display_path(state.wordlist_path)}",
            f"{indent}{word_count} words",
            "",
            APPLICATIONS_LABEL,
        ]
        tallies: list[str] = []
        if state.targets_ready:
            tallies.append(f"{indent}✓ {state.targets_ready} ready")
        if state.targets_needs_attention:
            tallies.append(f"{indent}! {state.targets_needs_attention} need attention")
        if state.targets_disabled:
            tallies.append(f"{indent}· {state.targets_disabled} disabled")
        if state.targets_unavailable:
            tallies.append(f"{indent}× {state.targets_unavailable} unavailable")
        if tallies:
            lines.extend(tallies)
        else:
            lines.append(f"{indent}{DASHBOARD_NO_APPS_LINE}")
        lines.extend(["", "Status", f"{indent}{state.overall_label}"])
        if state.last_operation_summary:
            lines.append(f"{indent}{state.last_operation_summary}")
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
                    "info": "→",
                }[notice.severity.value]
                issue_lines.append(f"  {prefix} {format_notice_summary(notice)}")
                issue_lines.append(f"     {format_notice_details(notice)}")
            self._set_optional_static("#dashboard-issues", "\n".join(issue_lines))
        else:
            self._set_optional_static("#dashboard-issues", "")

        self._blocked = (
            state.pending_recovery
            or state.overall_severity is DashboardSeverity.BLOCKED
            or self._controller.mutation_active
        )
        recovery_needed = state.pending_recovery or any(
            issue.code in {"pending_recovery", "corrupt_journal"} for issue in state.issues
        )
        apps_configured = _apps_configured(state)

        review_btn = self.query_one("#btn-review-update", Button)
        recovery_btn = self.query_one("#btn-recovery", Button)
        pull_btn = self.query_one("#btn-pull", Button)
        push_btn = self.query_one("#btn-push", Button)
        targets_btn = self.query_one("#btn-targets", Button)

        pull_btn.disabled = self._blocked
        push_btn.disabled = self._blocked

        if recovery_needed:
            review_btn.disabled = True
            review_btn.variant = "default"
            self._set_recovery_item_visible(True)
            recovery_btn.disabled = False
            recovery_btn.variant = "primary"
            recovery_btn.label = "Finish interrupted update"
            targets_btn.variant = "default"
            self._set_optional_static("#dashboard-next-step", "")
        elif not apps_configured:
            review_btn.disabled = self._blocked
            review_btn.variant = "default"
            self._set_recovery_item_visible(False)
            recovery_btn.disabled = True
            recovery_btn.variant = "default"
            targets_btn.variant = "primary"
            self._refresh_next_step(apps_configured=False)
        else:
            review_btn.disabled = self._blocked
            review_btn.variant = "primary"
            self._set_recovery_item_visible(False)
            recovery_btn.disabled = True
            recovery_btn.variant = "default"
            targets_btn.variant = "default"
            self._refresh_next_step(apps_configured=True)

        if state.pending_recovery:
            matching = [issue for issue in state.issues if issue.code == "pending_recovery"]
            if matching:
                notice = dashboard_issue_to_notice(matching[0])
            else:
                notice = build_notice("pending_recovery", severity=NoticeSeverity.BLOCKED)
            self._set_optional_static("#blocking-banner", format_notice_block(notice))
        elif any(issue.code == "invalid_config" for issue in state.issues):
            issue = next(i for i in state.issues if i.code == "invalid_config")
            self._set_optional_static(
                "#blocking-banner", format_notice_block(dashboard_issue_to_notice(issue))
            )
        elif any(issue.code == "unreadable_wordlist" for issue in state.issues):
            issue = next(i for i in state.issues if i.code == "unreadable_wordlist")
            self._set_optional_static(
                "#blocking-banner", format_notice_block(dashboard_issue_to_notice(issue))
            )
        elif any(issue.code == "corrupt_journal" for issue in state.issues):
            issue = next(i for i in state.issues if i.code == "corrupt_journal")
            self._set_optional_static(
                "#blocking-banner", format_notice_block(dashboard_issue_to_notice(issue))
            )
        else:
            self._set_optional_static("#blocking-banner", "")

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
        except OPERATIONAL_EXCEPTIONS:
            return None

    def on_load_dashboard_worker_state_changed(self, event) -> None:
        if event.state is WorkerState.RUNNING:
            return
        self._set_loading(False)
        if event.state is WorkerState.ERROR:
            if self._is_current_load(self._active_token):
                self._render_load_failure("× Dashboard unavailable — try Refresh.")
            return
        if event.state is not WorkerState.SUCCESS:
            return
        if not self._is_current_load(self._active_token):
            return
        payload = event.worker.result
        if payload is None:
            self._render_load_failure("× Dashboard load failed.")
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
        self._controller.clear_first_run_next_step()
        self._set_optional_static("#dashboard-next-step", "")
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
