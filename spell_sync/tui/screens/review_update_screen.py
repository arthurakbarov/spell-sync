"""Guided Review and update workflow (Phase 3)."""

from __future__ import annotations

from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Static
from textual.worker import Worker, WorkerState

from ...application.product_concepts import (
    COLLECT_WORDS_LABEL,
    PULL_DIRECTION_LABEL,
    PUSH_DIRECTION_LABEL,
    PUSH_FILTERING_NOTICE,
    PUSH_REDUNDANCY_PREVIEW_NOTICE,
    REVIEW_AND_UPDATE_LABEL,
    REVIEW_START_BODY,
    UPDATE_APPS_LABEL,
    pull_preview_additions_line,
)
from ...application.reports import OperationOutcome, OperationReport, PullPreview, PushPreview
from ..controller import TuiController
from ..export_results import ReportExportResult
from ..layout import action_bar, loading_message
from ..workers import LoadTokenMixin


def _format_pull_preview(preview: PullPreview) -> str:
    if preview.wordlist_error is not None or preview.prepare_error is not None:
        return f"× {COLLECT_WORDS_LABEL} preview unavailable."
    lines = [
        f"{COLLECT_WORDS_LABEL} review",
        "",
        PULL_DIRECTION_LABEL,
        "",
        pull_preview_additions_line(preview.additions),
        f"Sources ready: {len(preview.sources_used)}",
        f"Sources skipped: {len(preview.sources_skipped)}",
        f"Wordlist: {preview.wordlist_path}",
    ]
    if preview.warnings:
        lines.append("")
        lines.extend(f"  ! {warning}" for warning in preview.warnings)
    return "\n".join(lines)


def _format_push_preview(preview: PushPreview) -> str:
    if preview.wordlist_error is not None:
        return f"× {UPDATE_APPS_LABEL} preview unavailable (exit {int(preview.wordlist_error)})"
    if preview.prepare_error is not None:
        return f"× Push preview blocked (exit {int(preview.prepare_error)})"
    lines = [
        "Fresh push preview",
        "",
        PUSH_DIRECTION_LABEL,
        "",
        f"Targets to update: {preview.targets_to_update}",
        f"Total additions: {preview.additions}",
        f"Total removals: {preview.removals}",
        f"Unchanged: {preview.unchanged}",
        "",
        PUSH_FILTERING_NOTICE,
        "",
        PUSH_REDUNDANCY_PREVIEW_NOTICE,
    ]
    if preview.skipped:
        lines.append(f"Skipped: {', '.join(preview.skipped)}")
    if preview.warnings:
        lines.append(f"Warnings: {'; '.join(preview.warnings)}")
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

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="screen-body", classes="screen-body"):
            yield Static(id="review-pull-content")
        yield action_bar(
            Button(COLLECT_WORDS_LABEL, id="btn-pull", variant="primary"),
            Button("Skip collect", id="btn-skip"),
            Button("View additions", id="btn-additions"),
            Button("Back", id="btn-back"),
        )
        yield Footer()

    def on_mount(self) -> None:
        try:
            self._render_preview(self._controller.prepare_review_pull())
        except Exception:
            self.query_one("#review-pull-content", Static).update(
                f"× {COLLECT_WORDS_LABEL} preview load failed."
            )

    def _render_preview(self, preview: PullPreview) -> None:
        self._preview = preview
        pull_btn = self.query_one("#btn-pull", Button)
        skip_btn = self.query_one("#btn-skip", Button)
        self.query_one("#review-pull-content", Static).update(_format_pull_preview(preview))
        blocked = (
            preview.wordlist_error is not None
            or preview.prepare_error is not None
            or not preview.is_executable
            or self._controller.mutation_active
        )
        pull_btn.disabled = blocked or preview.additions == 0 or self._starting
        if preview.additions > 0:
            pull_btn.label = f"{COLLECT_WORDS_LABEL} (+{preview.additions})"
        else:
            pull_btn.label = COLLECT_WORDS_LABEL
        skip_btn.disabled = blocked or self._starting

    def action_run_pull(self) -> None:
        preview = self._preview
        if preview is None or not preview.is_executable or preview.additions == 0:
            self.notify("Pull preview is not ready.", severity="warning")
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
            self.notify("Pull preview is not ready.", severity="warning")
            return
        self._controller.mark_review_pull_skipped()
        self._controller.invalidate_push_preview()
        self.app.push_screen(ReviewPushScreen(self._controller))

    def action_view_additions(self) -> None:
        preview = self._preview
        if preview is None:
            return
        from .removals_screen import RemovalsScreen

        self.app.push_screen(
            RemovalsScreen(
                "additions",
                preview.addition_words,
                title="Pull additions",
            )
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-pull":
            self.action_run_pull()
        elif event.button.id == "btn-skip":
            self.action_skip_pull()
        elif event.button.id == "btn-additions":
            self.action_view_additions()
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
        yield action_bar(Button("Build Push preview", id="btn-build-push", variant="primary"))
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#review-pull-complete", Static).update(
            "Pull completed\n\nThe canonical wordlist changed.\nA fresh Push preview is required."
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-build-push":
            self.app.push_screen(ReviewPushScreen(self._controller))


class ReviewPushScreen(LoadTokenMixin, Screen[None]):
    BINDINGS = [
        ("escape", "back", "Back"),
        ("v", "view_removals", "View removals"),
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
            Button(UPDATE_APPS_LABEL, id="btn-push", variant="primary"),
            Button("View removals", id="btn-view-removals"),
            Button("Finish without update", id="btn-finish"),
            Button("Back", id="btn-back"),
        )
        yield Footer()

    def on_mount(self) -> None:
        self._load_fresh_preview()

    def _load_fresh_preview(self) -> None:
        self._active_token = self._begin_load()
        self._set_loading(True)
        self.query_one("#review-push-content", Static).update(
            loading_message("Loading push preview...", "push_preview")
        )
        self._worker = self.load_push_preview_worker()
        self.set_interval(0.05, self._poll_push_worker, repeat=40)

    def _poll_push_worker(self) -> None:
        worker = getattr(self, "_worker", None)
        if worker is None or not self.is_mounted:
            return
        if worker.state is WorkerState.ERROR:
            self._set_loading(False)
            self.query_one("#review-push-content", Static).update("× Push preview unavailable.")
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
        except Exception:
            return PushPreview(
                prepared=None,
                targets=(),
                additions=0,
                removals=0,
                warnings=(),
                created_at="",
                plan_identifier="error",
                targets_to_update=0,
                unchanged=0,
                skipped=(),
                corrupt=(),
                blocked=(),
            )

    def on_load_push_preview_worker_state_changed(self, event) -> None:
        if event.state is WorkerState.RUNNING:
            return
        self._set_loading(False)
        if event.state is WorkerState.ERROR:
            if self.is_mounted:
                self.query_one("#review-push-content", Static).update("× Push preview unavailable.")
            return
        if event.state is not WorkerState.SUCCESS:
            return
        if self._active_token != self._load_generation:
            return
        self._render_preview(event.worker.result)
        self._worker = None

    def _set_loading(self, loading: bool) -> None:
        self.query_one("#btn-view-removals", Button).disabled = loading
        if loading:
            self.query_one("#btn-push", Button).disabled = True
            self.query_one("#btn-finish", Button).disabled = True

    def _render_preview(self, preview: PushPreview) -> None:
        self._preview = preview
        table = self.query_one("#review-push-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Target", "Add", "Remove", "Status")
        for target in preview.targets:
            table.add_row(
                target.name,
                str(target.additions),
                str(target.removals),
                target.status,
            )
        self.query_one("#review-push-content", Static).update(_format_push_preview(preview))
        push_btn = self.query_one("#btn-push", Button)
        finish_btn = self.query_one("#btn-finish", Button)
        can_push = (
            preview.is_executable
            and preview.prepared is not None
            and preview.targets_to_update > 0
            and not self._controller.mutation_active
            and not self._starting
        )
        push_btn.disabled = not can_push
        finish_btn.disabled = self._controller.mutation_active or self._starting

    def _selected_target(self):
        preview = self._preview
        if preview is None or not preview.targets:
            return None
        table = self.query_one("#review-push-table", DataTable)
        if table.row_count == 0:
            return preview.targets[0]
        cursor_row = table.cursor_row
        if cursor_row is None or cursor_row < 0 or cursor_row >= len(preview.targets):
            return preview.targets[0]
        return preview.targets[cursor_row]

    def action_view_removals(self) -> None:
        target = self._selected_target()
        if target is None:
            self.notify("No preview loaded.", severity="warning")
            return
        from .removals_screen import RemovalsScreen

        self.app.push_screen(RemovalsScreen(target.name, target.removal_words))

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
            self.notify("Push is not available for this preview.", severity="warning")
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
        self._controller.mark_review_push_skipped()
        self.app.push_screen(ReviewSessionReportScreen(self._controller))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-view-removals":
            self.action_view_removals()
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
            yield Static(id="session-report-export-status")
        yield action_bar(
            Button("Back to dashboard", id="btn-dashboard", variant="primary"),
            Button("Save report", id="btn-save-report"),
            Button("View operation history", id="btn-history"),
            Button("Quit", id="btn-quit", variant="error"),
        )
        yield Footer()

    def on_mount(self) -> None:
        report = self._controller.build_review_session_report()
        self.query_one("#review-session-report", Static).update("\n".join(report.summary_lines))

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
            status.update(
                "Report already saved\n\n"
                f"{redact_path(self._saved_report_path) or self._saved_report_path}"
            )
            return
        if self._export_in_progress:
            return
        self._export_in_progress = True
        self._export_token = self._begin_export()
        self._export_started_token = self._export_token
        self.query_one("#btn-save-report", Button).disabled = True
        status.update("Saving report...")
        self._export_worker_handle = self.export_session_report_worker()
        self.set_interval(0.05, self._poll_export_worker, repeat=40)

    def _poll_export_worker(self) -> None:
        worker = getattr(self, "_export_worker_handle", None)
        if worker is None or worker.state is WorkerState.RUNNING:
            return
        self._finish_export_worker(worker)

    def _finish_export_worker(self, worker) -> None:
        from ...support.path_redaction import redact_path

        if not self._export_in_progress:
            return
        self._export_in_progress = False
        if self.is_mounted:
            self.query_one("#btn-save-report", Button).disabled = False
        if worker.state is WorkerState.ERROR:
            if self.is_mounted:
                self.query_one("#session-report-export-status", Static).update(
                    "× Review report could not be exported."
                )
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
        if not isinstance(export_result, ReportExportResult):
            return
        status = self.query_one("#session-report-export-status", Static)
        if export_result.ok and export_result.path is not None:
            self._saved_report_path = export_result.path
            redacted = redact_path(export_result.path) or export_result.path
            status.update(f"Report saved\n\n{redacted}")
            return
        status.update(f"× {export_result.message or 'Review report could not be exported.'}")

    @work(thread=True, exclusive=True, group="session-report-export")
    def export_session_report_worker(self) -> ReportExportResult:
        try:
            path = self._controller.export_review_session_report(fmt="json")
            return ReportExportResult(ok=True, path=str(path))
        except FileExistsError as exc:
            return ReportExportResult(ok=False, message=str(exc))
        except Exception:
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
