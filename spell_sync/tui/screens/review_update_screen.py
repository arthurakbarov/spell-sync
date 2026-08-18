"""Guided Review and update workflow."""

from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Static
from textual.worker import Worker, WorkerState

from ...application.product_concepts import (
    ADD_WORDS_LABEL,
    COLLECT_WORDS_LABEL,
    CONTINUE_TO_REVIEW_SUMMARY_LABEL,
    CONTINUE_TO_UPDATE_APPS_LABEL,
    DICTIONARY_TABLE_COLUMN,
    FINISH_WITHOUT_UPDATE_LABEL,
    PULL_DIRECTION_LABEL,
    PUSH_PREVIEW_EMPTY_NEXT,
    REVIEW_AND_UPDATE_LABEL,
    REVIEW_EXTRA_WORDS_LABEL,
    REVIEW_PULL_COMPLETE_BODY,
    REVIEW_SESSION_DONE_PARTIAL,
    REVIEW_START_BODY,
    SKIP_COLLECT_LABEL,
    UPDATE_APPS_LABEL,
    pull_preview_additions_line,
    pull_preview_dictionary_count_lines,
    pull_preview_empty_next_line,
    pull_preview_unavailable_message,
    pull_preview_warning_lines,
    push_preview_unavailable_message,
    review_session_done_matched,
    written_includes_editors,
)
from ...application.push_preview_copy import (
    format_push_preview_summary,
    push_detail_buttons_visible,
)
from ...application.reports import OperationOutcome, OperationReport, PullPreview, PushPreview
from ...exit_codes import ExitCode
from ..context_next import continue_from_collect_preview
from ..controller import TuiController
from ..export_results import ReportExportResult
from ..layout import action_bar, loading_message, set_optional_static, sync_data_table_rows
from ..operational import OPERATIONAL_EXCEPTIONS
from ..workers import LoadTokenMixin


def _format_pull_preview(preview: PullPreview) -> str:
    if preview.wordlist_error is not None or preview.prepare_error is not None:
        return pull_preview_unavailable_message()
    lines = [
        f"{COLLECT_WORDS_LABEL}",
        "",
        PULL_DIRECTION_LABEL,
        "",
        pull_preview_additions_line(preview.additions, before_count=preview.before_count),
    ]
    if preview.additions == 0:
        lines.extend(["", pull_preview_empty_next_line(before_count=preview.before_count)])
    else:
        lines.append("")
        lines.extend(
            pull_preview_dictionary_count_lines(
                ready=len(preview.sources_used),
                skipped=len(preview.sources_skipped),
            )
        )
    if preview.warnings:
        lines.append("")
        lines.extend(pull_preview_warning_lines(preview.warnings))
    return "\n".join(lines)


def _review_should_end(report: OperationReport) -> bool:
    return report.recovery_required or report.outcome in {
        OperationOutcome.RECOVERY_REQUIRED,
        OperationOutcome.FAILED,
        OperationOutcome.STOPPED_SAFELY,
    }


class ReviewStartScreen(Screen[None]):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="screen-body", classes="screen-body"):
            yield Static(REVIEW_AND_UPDATE_LABEL, id="review-title")
            yield Static(id="review-body")
            yield action_bar(
                Button("Start review", id="btn-start", variant="primary"),
                Button("Back", id="btn-back"),
            )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#review-body", Static).update(REVIEW_START_BODY)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-start":
            self._controller.begin_review_session()
            self.app.switch_screen(ReviewPullScreen(self._controller))
        elif event.button.id == "btn-back":
            self.action_back()

    def action_back(self) -> None:
        self._controller.clear_review_session()
        self.app.pop_screen()


class ReviewPullScreen(LoadTokenMixin, Screen[None]):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller
        self._preview: PullPreview | None = None
        self._starting = False
        self._refresh_on_resume = False

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="screen-body", classes="screen-body"):
            yield Static(id="review-pull-content")
            yield action_bar(
                Button(COLLECT_WORDS_LABEL, id="btn-pull", variant="primary"),
                Button(SKIP_COLLECT_LABEL, id="btn-skip"),
                Button("View additions", id="btn-additions"),
                Button(REVIEW_EXTRA_WORDS_LABEL, id="btn-extra-words"),
                Button("Back", id="btn-back"),
            )
        yield Footer()

    def on_mount(self) -> None:
        try:
            self._render_preview(self._controller.prepare_review_pull())
        except OPERATIONAL_EXCEPTIONS:
            self.query_one("#review-pull-content", Static).update(
                f"× {COLLECT_WORDS_LABEL} preview load failed."
            )
            self.query_one("#btn-extra-words", Button).display = False

    def on_screen_resume(self) -> None:
        if self._starting or not self.is_mounted or self.app.screen is not self:
            return
        if not self._refresh_on_resume:
            return
        self._refresh_on_resume = False
        try:
            self._render_preview(self._controller.prepare_review_pull())
        except OPERATIONAL_EXCEPTIONS:
            self.query_one("#review-pull-content", Static).update(
                f"× {COLLECT_WORDS_LABEL} preview load failed."
            )
            self.query_one("#btn-extra-words", Button).display = False

    def _render_preview(self, preview: PullPreview) -> None:
        self._preview = preview
        pull_btn = self.query_one("#btn-pull", Button)
        skip_btn = self.query_one("#btn-skip", Button)
        additions_btn = self.query_one("#btn-additions", Button)
        extra_btn = self.query_one("#btn-extra-words", Button)
        self.query_one("#review-pull-content", Static).update(_format_pull_preview(preview))
        blocked = (
            preview.wordlist_error is not None
            or preview.prepare_error is not None
            or not preview.is_executable
            or self._controller.mutation_active
        )
        has_additions = preview.additions > 0
        list_empty = preview.before_count == 0
        # Empty list → Add words (including Skip collect). Else Update when
        # Collect has nothing to add.
        additions_btn.display = has_additions
        extra_btn.display = has_additions
        extra_btn.disabled = self._starting or self._controller.mutation_active
        pull_btn.display = has_additions
        if has_additions:
            pull_btn.disabled = blocked or self._starting
            pull_btn.variant = "primary"
            pull_btn.label = f"{COLLECT_WORDS_LABEL} (+{preview.additions})"
            skip_btn.label = SKIP_COLLECT_LABEL
            skip_btn.variant = "default"
        elif list_empty:
            pull_btn.disabled = True
            pull_btn.variant = "default"
            pull_btn.label = COLLECT_WORDS_LABEL
            skip_btn.label = ADD_WORDS_LABEL
            skip_btn.variant = "primary"
        else:
            pull_btn.disabled = True
            pull_btn.variant = "default"
            pull_btn.label = COLLECT_WORDS_LABEL
            skip_btn.label = CONTINUE_TO_UPDATE_APPS_LABEL
            skip_btn.variant = "primary"
        skip_btn.disabled = blocked or self._starting

    def action_run_pull(self) -> None:
        preview = self._preview
        if preview is None or not preview.is_executable or preview.additions == 0:
            self.notify(f"{COLLECT_WORDS_LABEL} preview is not ready.", severity="warning")
            return
        if self._controller.mutation_active or self._starting:
            self.notify("An operation is already running.", severity="warning")
            return
        from .pull_confirm_screen import PullConfirmScreen

        self._starting = True
        self.query_one("#btn-pull", Button).disabled = True
        self.app.push_screen(
            PullConfirmScreen(self._controller, preview),
            lambda confirmed: self._after_pull_confirm(preview, confirmed),
        )

    def _after_pull_confirm(self, preview: PullPreview, confirmed: bool | None) -> None:
        from .operation_screen import OperationScreen

        self._starting = False
        if not self.is_mounted:
            return
        self._render_preview(preview)
        if not confirmed:
            return
        self.app.push_screen(
            OperationScreen(
                self._controller,
                operation="pull",
                pull_preview=preview,
                on_complete=self._on_pull_complete,
            )
        )

    def _on_pull_complete(self, report: OperationReport) -> None:
        self._controller.record_review_pull_report(report)
        if _review_should_end(report):
            self.app.push_screen(ReviewSessionReportScreen(self._controller))
            return
        if report.outcome in {OperationOutcome.COMPLETED, OperationOutcome.COMPLETED_WITH_WARNINGS}:
            self.app.push_screen(ReviewPullCompleteScreen(self._controller))
            return
        self.app.push_screen(ReviewSessionReportScreen(self._controller))

    def action_skip_pull(self) -> None:
        if self._starting or self._controller.mutation_active:
            return
        preview = self._preview
        if preview is None or not preview.is_executable:
            self.notify(f"{COLLECT_WORDS_LABEL} preview is not ready.", severity="warning")
            return
        self._refresh_on_resume = continue_from_collect_preview(self.app, self._controller, preview)

    def action_open_extra_words(self) -> None:
        from .extra_words_screen import ExtraWordsScreen

        self._refresh_on_resume = True
        self.app.push_screen(ExtraWordsScreen(self._controller))

    def action_view_additions(self) -> None:
        preview = self._preview
        if preview is None:
            return
        from .removals_screen import RemovalsScreen

        self.app.push_screen(
            RemovalsScreen(
                "additions",
                preview.addition_words,
                title=f"{COLLECT_WORDS_LABEL} additions",
            )
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-pull":
            self.action_run_pull()
        elif event.button.id == "btn-skip":
            self.action_skip_pull()
        elif event.button.id == "btn-additions":
            self.action_view_additions()
        elif event.button.id == "btn-extra-words":
            self.action_open_extra_words()
        elif event.button.id == "btn-back":
            self.action_back()

    def action_back(self) -> None:
        self._controller.clear_review_session()
        self.app.pop_screen()


class ReviewPullCompleteScreen(Screen[None]):
    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="screen-body", classes="screen-body"):
            yield Static(id="review-pull-complete")
            yield action_bar(
                Button(
                    CONTINUE_TO_UPDATE_APPS_LABEL,
                    id="btn-build-push",
                    variant="primary",
                )
            )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#review-pull-complete", Static).update(REVIEW_PULL_COMPLETE_BODY)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-build-push":
            self.app.push_screen(ReviewPushScreen(self._controller))


class ReviewPushScreen(LoadTokenMixin, Screen[None]):
    BINDINGS = [
        ("escape", "back", "Back"),
        ("v", "view_removals", "View removals"),
        ("a", "view_additions", "View additions"),
    ]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller
        self._preview: PushPreview | None = None
        self._starting = False
        self._active_token = 0
        self._worker: Any = None

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="screen-body", classes="screen-body"):
            yield Static(id="review-push-content")
            yield DataTable(id="review-push-table")
            yield action_bar(
                Button(CONTINUE_TO_UPDATE_APPS_LABEL, id="btn-push", variant="primary"),
                Button("View removals", id="btn-view-removals"),
                Button("View additions", id="btn-view-additions"),
                Button(FINISH_WITHOUT_UPDATE_LABEL, id="btn-finish"),
                Button("Back", id="btn-back"),
            )
        yield Footer()

    def on_mount(self) -> None:
        self._load_fresh_preview()

    def _sync_finish_button(self, *, can_push: bool) -> None:
        finish_btn = self.query_one("#btn-finish", Button)
        finish_btn.disabled = self._controller.mutation_active or self._starting
        if can_push:
            finish_btn.label = FINISH_WITHOUT_UPDATE_LABEL
            finish_btn.variant = "default"
        else:
            # Update hidden: this is the only forward step — not an optional skip.
            finish_btn.label = CONTINUE_TO_REVIEW_SUMMARY_LABEL
            finish_btn.variant = "primary"

    def _load_fresh_preview(self) -> None:
        self._active_token = self._begin_load()
        self._set_loading(True)
        self.query_one("#review-push-content", Static).update(
            loading_message(f"Loading {UPDATE_APPS_LABEL} preview...", "push_preview")
        )
        self._worker = self.load_push_preview_worker()
        self.set_interval(0.05, self._poll_push_worker, repeat=40)

    def _poll_push_worker(self) -> None:
        worker = getattr(self, "_worker", None)
        if worker is None or not self.is_mounted:
            return
        if worker.state is WorkerState.ERROR:
            self._set_loading(False)
            self.query_one("#review-push-content", Static).update(
                f"{push_preview_unavailable_message()}\n\n{PUSH_PREVIEW_EMPTY_NEXT}"
            )
            table = self.query_one("#review-push-table", DataTable)
            table.clear(columns=True)
            sync_data_table_rows(table)
            self.query_one("#btn-view-additions", Button).display = False
            self.query_one("#btn-view-removals", Button).display = False
            push_btn = self.query_one("#btn-push", Button)
            push_btn.display = False
            push_btn.disabled = True
            self._sync_finish_button(can_push=False)
            self._worker = None
            return
        if worker.state is WorkerState.SUCCESS:
            self._set_loading(False)
            if self._active_token == self._load_generation:
                self._render_preview(worker.result)
            self._worker = None

    @work(thread=True, exclusive=True, group="review-push-load")
    def load_push_preview_worker(self) -> PushPreview:
        try:
            return self._controller.prepare_review_push()
        except OPERATIONAL_EXCEPTIONS:
            return PushPreview.unavailable(
                plan_identifier="error",
                prepare_error=ExitCode.PUSH_ABORT,
            )

    def on_load_push_preview_worker_state_changed(self, event) -> None:
        if event.state is WorkerState.RUNNING:
            return
        self._set_loading(False)
        if event.state is WorkerState.ERROR:
            if self.is_mounted:
                self.query_one("#review-push-content", Static).update(
                    f"{push_preview_unavailable_message()}\n\n{PUSH_PREVIEW_EMPTY_NEXT}"
                )
                table = self.query_one("#review-push-table", DataTable)
                table.clear(columns=True)
                sync_data_table_rows(table)
                self.query_one("#btn-view-additions", Button).display = False
                self.query_one("#btn-view-removals", Button).display = False
                push_btn = self.query_one("#btn-push", Button)
                push_btn.display = False
                push_btn.disabled = True
                self._sync_finish_button(can_push=False)
            return
        if event.state is not WorkerState.SUCCESS:
            return
        if self._active_token != self._load_generation:
            return
        self._render_preview(event.worker.result)
        self._worker = None

    def _set_loading(self, loading: bool) -> None:
        self.query_one("#btn-view-removals", Button).disabled = loading
        self.query_one("#btn-view-additions", Button).disabled = loading
        self.query_one("#btn-push", Button).disabled = loading
        self.query_one("#btn-finish", Button).disabled = loading

    def _render_preview(self, preview: PushPreview) -> None:
        self._preview = preview
        table = self.query_one("#review-push-table", DataTable)
        table.clear(columns=True)
        table.add_columns(DICTIONARY_TABLE_COLUMN, "Add", "Remove", "Status")
        for target in preview.targets:
            table.add_row(
                target.name,
                str(target.additions),
                str(target.removals),
                target.status,
            )
        sync_data_table_rows(table)
        content = self.query_one("#review-push-content", Static)
        add_btn = self.query_one("#btn-view-additions", Button)
        rem_btn = self.query_one("#btn-view-removals", Button)
        can_push = (
            preview.is_executable
            and preview.prepared is not None
            and preview.targets_to_update > 0
            and not self._controller.mutation_active
            and not self._starting
        )
        if preview.wordlist_error is not None or preview.prepare_error is not None:
            content.update(f"{push_preview_unavailable_message()}\n\n{PUSH_PREVIEW_EMPTY_NEXT}")
            add_btn.display = False
            rem_btn.display = False
        else:
            summary = format_push_preview_summary(
                preview,
                title=f"{UPDATE_APPS_LABEL} preview",
                include_safety=False,
            )
            if not can_push:
                summary = f"{summary}\n\n{PUSH_PREVIEW_EMPTY_NEXT}"
            content.update(summary)
            has_additions, has_removals = push_detail_buttons_visible(preview)
            add_btn.display = has_additions
            rem_btn.display = has_removals
        push_btn = self.query_one("#btn-push", Button)
        # No dictionaries to update: hide dead Update; Continue to summary is the next step.
        push_btn.display = can_push
        push_btn.disabled = not can_push
        push_btn.variant = "primary" if can_push else "default"
        self._sync_finish_button(can_push=can_push)

    def action_view_removals(self) -> None:
        preview = self._preview
        if preview is None:
            self.notify("No preview loaded.", severity="warning")
            return
        from .removals_screen import removals_screen_for_push_preview

        self.app.push_screen(removals_screen_for_push_preview(preview))

    def action_view_additions(self) -> None:
        preview = self._preview
        if preview is None:
            self.notify("No preview loaded.", severity="warning")
            return
        from .removals_screen import additions_screen_for_push_preview

        self.app.push_screen(additions_screen_for_push_preview(preview))

    def action_run_push(self) -> None:
        preview = self._preview
        if (
            preview is None
            or not preview.is_executable
            or preview.prepared is None
            or preview.targets_to_update == 0
            or self._controller.mutation_active
            or self._starting
        ):
            self.notify(
                f"{UPDATE_APPS_LABEL} is not available for this preview.", severity="warning"
            )
            return
        from .push_confirm_screen import PushConfirmScreen

        self._starting = True
        self.query_one("#btn-push", Button).disabled = True
        self.app.push_screen(
            PushConfirmScreen(self._controller, preview),
            lambda confirmed: self._after_push_confirm(preview, confirmed),
        )

    def _after_push_confirm(self, preview: PushPreview, confirmed: bool | None) -> None:
        from .operation_screen import OperationScreen

        self._starting = False
        if not self.is_mounted:
            return
        self._render_preview(preview)
        if not confirmed:
            return
        self.app.push_screen(
            OperationScreen(
                self._controller,
                operation="push",
                push_preview=preview,
                on_complete=self._on_push_complete,
            )
        )

    def _on_push_complete(self, report: OperationReport) -> None:
        self._controller.record_review_push_report(report)
        self.app.push_screen(ReviewSessionReportScreen(self._controller))

    def action_finish_without_push(self) -> None:
        if self._starting or self._controller.mutation_active:
            return
        preview = self._preview
        nothing_to_update = (
            preview is not None and preview.is_executable and preview.targets_to_update == 0
        )
        # Only mark Skipped when Update was a real choice the guest declined.
        if not nothing_to_update:
            self._controller.mark_review_push_skipped()
        self.app.push_screen(ReviewSessionReportScreen(self._controller))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-view-removals":
            self.action_view_removals()
        elif event.button.id == "btn-view-additions":
            self.action_view_additions()
        elif event.button.id == "btn-push":
            self.action_run_push()
        elif event.button.id == "btn-finish":
            self.action_finish_without_push()
        elif event.button.id == "btn-back":
            self.action_back()

    def action_back(self) -> None:
        self._controller.invalidate_push_preview()
        self.app.pop_screen()


class ReviewSessionReportScreen(LoadTokenMixin, Screen[None]):
    BINDINGS = [("escape", "back_dashboard", "Back")]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller
        self._saved_report_path: str | None = None
        self._export_generation = 0
        self._export_in_progress = False
        self._export_token = 0
        self._export_started_token = 0
        self._export_worker_handle: Worker | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="screen-body", classes="screen-body"):
            yield Static(id="review-session-report")
            yield action_bar(
                Button("Back to dashboard", id="btn-dashboard", variant="primary"),
                Button("Save report", id="btn-save-report"),
                Button("View operation history", id="btn-history"),
                Button("Quit", id="btn-quit", variant="error"),
                status_id="session-report-export-status",
            )
        yield Footer()

    def on_mount(self) -> None:
        report = self._controller.build_review_session_report()
        session = self._controller.review_session()
        editors_updated = False
        if session is not None and session.push_report is not None:
            editors_updated = written_includes_editors(
                row.name for row in session.push_report.target_updates if row.status == "Updated"
            )
        done = (
            review_session_done_matched(editors_updated=editors_updated)
            if report.is_matched
            else REVIEW_SESSION_DONE_PARTIAL
        )
        lines = list(report.summary_lines)
        lines.extend(["", done])
        self.query_one("#review-session-report", Static).update("\n".join(lines))
        # Empty export status must not reserve a hole above Back to dashboard.
        set_optional_static(self.query_one("#session-report-export-status", Static), "")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save-report":
            self._save_session_report()
        elif event.button.id == "btn-dashboard":
            self.action_back_dashboard()
        elif event.button.id == "btn-history":
            from .logs_screen import LogsScreen

            self.app.push_screen(LogsScreen(self._controller))
        elif event.button.id == "btn-quit":
            self._controller.clear_review_session()
            self.app.exit(0)

    def _begin_export(self) -> int:
        self._export_generation += 1
        return self._export_generation

    def _is_current_export(self) -> bool:
        return self._export_started_token == self._export_token and self.is_mounted

    def _save_session_report(self) -> None:
        from ...support.path_redaction import redact_path

        status = self.query_one("#session-report-export-status", Static)
        if self._saved_report_path is not None:
            set_optional_static(
                status,
                "Report already saved\n"
                f"{redact_path(self._saved_report_path) or self._saved_report_path}",
            )
            return
        if self._export_in_progress:
            return
        self._export_in_progress = True
        self._export_token = self._begin_export()
        self._export_started_token = self._export_token
        self.query_one("#btn-save-report", Button).disabled = True
        set_optional_static(status, "Saving report...")
        self._export_worker_handle = self.export_session_report_worker()
        self.set_interval(0.05, self._poll_export_worker, repeat=40)

    def _poll_export_worker(self) -> None:
        worker = getattr(self, "_export_worker_handle", None)
        if worker is None or worker.state is WorkerState.RUNNING:
            return
        self._finish_export_worker(worker)

    def _finish_export_worker(self, worker: Worker | None) -> None:
        from ...support.path_redaction import redact_path

        if worker is None or not self._export_in_progress:
            return
        if worker is not self._export_worker_handle:
            return
        if worker.state in (WorkerState.PENDING, WorkerState.RUNNING):
            return
        self._export_in_progress = False
        if self.is_mounted:
            self.query_one("#btn-save-report", Button).disabled = False
        status = (
            self.query_one("#session-report-export-status", Static) if self.is_mounted else None
        )
        if worker.state is WorkerState.ERROR:
            if status is not None:
                set_optional_static(status, "× Review report could not be exported.")
            self._export_worker_handle = None
            return
        if worker.state is not WorkerState.SUCCESS:
            self._export_worker_handle = None
            return
        if not self._is_current_export():
            self._export_worker_handle = None
            return
        export_result = worker.result
        self._export_worker_handle = None
        if not isinstance(export_result, ReportExportResult) or status is None:
            return
        if export_result.ok and export_result.path is not None:
            self._saved_report_path = export_result.path
            redacted = redact_path(export_result.path) or export_result.path
            set_optional_static(status, f"Report saved\n{redacted}")
            return
        set_optional_static(
            status,
            f"× {export_result.message or 'Review report could not be exported.'}",
        )

    @work(thread=True, exclusive=True, group="session-report-export")
    def export_session_report_worker(self) -> ReportExportResult:
        try:
            path = self._controller.export_review_session_report(fmt="json")
            return ReportExportResult(ok=True, path=str(path))
        except FileExistsError as exc:
            return ReportExportResult(ok=False, message=str(exc))
        except OPERATIONAL_EXCEPTIONS:
            return ReportExportResult(
                ok=False,
                message="Review report could not be exported.",
            )

    def on_export_session_report_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state is WorkerState.RUNNING:
            return
        self._finish_export_worker(event.worker)

    def action_back_dashboard(self) -> None:
        from .dashboard import DashboardScreen

        self._controller.clear_review_session()
        while not isinstance(self.app.screen, DashboardScreen):
            if len(self.app.screen_stack) <= 1:
                break
            self.app.pop_screen()
        screen = self.app.screen
        if isinstance(screen, DashboardScreen):
            screen.action_refresh_dashboard()
