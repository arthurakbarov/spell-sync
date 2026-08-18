"""Pull preview screen."""

from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Static
from textual.worker import WorkerState

from ...application.product_concepts import (
    ADD_WORDS_LABEL,
    COLLECT_WORDS_LABEL,
    CONTINUE_TO_UPDATE_APPS_LABEL,
    PULL_DIRECTION_LABEL,
    PULL_PREVIEW_SAFETY,
    PULL_SCOPE_NOTICE,
    REVIEW_EXTRA_WORDS_LABEL,
    pull_preview_additions_line,
    pull_preview_dictionary_count_lines,
    pull_preview_empty_next_line,
    pull_preview_unavailable_message,
    pull_preview_warning_lines,
)
from ...application.reports import PullPreview
from ...exit_codes import ExitCode
from ..context_next import continue_from_collect_preview
from ..controller import TuiController
from ..layout import action_bar, loading_message, sync_data_table_rows
from ..operational import OPERATIONAL_EXCEPTIONS
from ..workers import LoadTokenMixin


class PullScreen(LoadTokenMixin, Screen[None]):
    BINDINGS = [
        ("escape", "back", "Back"),
        ("r", "refresh_preview", "Refresh"),
    ]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller
        self._preview: PullPreview | None = None
        self._active_token = 0
        self._starting = False
        self._refresh_on_resume = False
        self._worker: Any = None

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="screen-body", classes="screen-body"):
            yield Static(id="pull-summary", classes="screen-prose")
            yield DataTable(id="pull-table")
            yield action_bar(
                Button(COLLECT_WORDS_LABEL, id="btn-run", variant="primary"),
                Button(CONTINUE_TO_UPDATE_APPS_LABEL, id="btn-next-step"),
                Button(REVIEW_EXTRA_WORDS_LABEL, id="btn-extra-words"),
                Button("View additions", id="btn-view-additions"),
                Button("Refresh preview", id="btn-refresh"),
                Button("Back", id="btn-back"),
            )
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#pull-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Source", "Status", "Added", "Detail")
        try:
            self._render_preview(self._controller.prepare_pull())
        except OPERATIONAL_EXCEPTIONS:
            self.query_one("#pull-summary", Static).update(pull_preview_unavailable_message())
            self.query_one("#btn-next-step", Button).display = False
            table = self.query_one("#pull-table", DataTable)
            table.clear()
            sync_data_table_rows(table)

    def _set_loading(self, loading: bool) -> None:
        self.query_one("#btn-refresh", Button).disabled = loading
        self.query_one("#btn-run", Button).disabled = loading or self._starting
        self.query_one("#btn-next-step", Button).disabled = loading or self._starting
        self.query_one("#btn-extra-words", Button).disabled = loading or self._starting

    def _render_preview(self, preview: PullPreview) -> None:
        self._preview = preview
        body = self.query_one("#pull-summary", Static)
        table = self.query_one("#pull-table", DataTable)
        table.clear()
        run_btn = self.query_one("#btn-run", Button)
        back = self.query_one("#btn-back", Button)
        if preview.wordlist_error is not None or preview.prepare_error is not None:
            body.update(pull_preview_unavailable_message())
            run_btn.display = False
            run_btn.disabled = True
            run_btn.variant = "default"
            self.query_one("#btn-view-additions", Button).display = False
            self.query_one("#btn-extra-words", Button).display = False
            self.query_one("#btn-next-step", Button).display = False
            back.variant = "primary"
            sync_data_table_rows(table)
            return
        lines = [
            f"{COLLECT_WORDS_LABEL} preview (no writes yet)",
            PULL_PREVIEW_SAFETY,
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
        lines.append(PULL_SCOPE_NOTICE)
        if preview.warnings:
            lines.append("")
            lines.extend(pull_preview_warning_lines(preview.warnings))
        body.update("\n".join(lines))
        for row in preview.source_rows:
            table.add_row(
                row.name,
                row.status,
                f"+{row.words_contributed}",
                row.detail or "",
            )
        sync_data_table_rows(table)
        has_work = (
            preview.additions > 0 and preview.is_executable and not self._controller.mutation_active
        )
        run_btn.display = has_work
        run_btn.disabled = not has_work
        run_btn.variant = "primary" if has_work else "default"
        self.query_one("#btn-view-additions", Button).display = preview.additions > 0
        self.query_one("#btn-extra-words", Button).display = preview.additions > 0
        next_btn = self.query_one("#btn-next-step", Button)
        list_empty = preview.before_count == 0
        empty_collect = preview.additions == 0
        next_btn.display = empty_collect
        if empty_collect:
            if list_empty:
                next_btn.label = ADD_WORDS_LABEL
            else:
                next_btn.label = CONTINUE_TO_UPDATE_APPS_LABEL
            next_btn.variant = "primary"
            next_btn.disabled = self._starting or self._controller.mutation_active
            back.variant = "default"
        else:
            next_btn.variant = "default"
            back.variant = "default" if has_work else "primary"

    def on_screen_resume(self) -> None:
        if self._starting or not self.is_mounted or self.app.screen is not self:
            return
        if not self._refresh_on_resume:
            return
        self._refresh_on_resume = False
        self.refresh_preview()

    def refresh_preview(self) -> None:
        self._controller.invalidate_pull_preview()
        self._preview = None
        self._active_token = self._begin_load()
        self._set_loading(True)
        self.query_one("#pull-summary", Static).update(
            loading_message(f"Loading {COLLECT_WORDS_LABEL} preview...", "pull_preview")
        )
        self._worker = self.load_pull_worker()
        self.set_interval(0.05, self._poll_pull_worker, repeat=40)

    @work(thread=True, exclusive=True, group="pull-load")
    def load_pull_worker(self) -> PullPreview:
        try:
            return self._controller.prepare_pull()
        except OPERATIONAL_EXCEPTIONS:
            return PullPreview.unavailable(
                wordlist_path="",
                plan_identifier="error",
                prepare_error=ExitCode.PUSH_ABORT,
            )

    def _poll_pull_worker(self) -> None:
        worker = getattr(self, "_worker", None)
        if worker is None or not self.is_mounted:
            return
        if worker.state is WorkerState.ERROR:
            self._set_loading(False)
            self.query_one("#pull-summary", Static).update(
                f"{pull_preview_unavailable_message()} Try Refresh."
            )
            table = self.query_one("#pull-table", DataTable)
            table.clear()
            sync_data_table_rows(table)
            self._worker = None
            return
        if worker.state is WorkerState.SUCCESS:
            self._set_loading(False)
            if self._active_token == self._load_generation:
                self._render_preview(worker.result)
            self._worker = None

    def on_load_pull_worker_state_changed(self, event) -> None:
        if event.state is WorkerState.RUNNING:
            return
        self._set_loading(False)
        if event.state is WorkerState.ERROR:
            if self.is_mounted:
                self.query_one("#pull-summary", Static).update(
                    f"{pull_preview_unavailable_message()} Try Refresh."
                )
                table = self.query_one("#pull-table", DataTable)
                table.clear()
                sync_data_table_rows(table)
            return
        if event.state is not WorkerState.SUCCESS:
            return
        if self._active_token != self._load_generation:
            return
        self._render_preview(event.worker.result)
        self._worker = None

    def action_refresh_preview(self) -> None:
        self.refresh_preview()

    def action_run_pull(self) -> None:
        preview = self._preview
        if preview is None or not preview.is_executable:
            self.notify(f"{COLLECT_WORDS_LABEL} preview is not ready.", severity="warning")
            return
        if self._controller.mutation_active or self._starting:
            self.notify("An operation is already running.", severity="warning")
            return
        self._starting = True
        self.query_one("#btn-run", Button).disabled = True

        def _after_confirm(confirmed: bool | None) -> None:
            self._starting = False
            if not self.is_mounted:
                return
            self.query_one("#btn-run", Button).disabled = False
            if not confirmed:
                return
            from .operation_screen import OperationScreen

            self.app.push_screen(
                OperationScreen(
                    self._controller,
                    operation="pull",
                    pull_preview=preview,
                )
            )

        from .pull_confirm_screen import PullConfirmScreen

        self.app.push_screen(PullConfirmScreen(self._controller, preview), _after_confirm)

    def action_empty_collect_next(self) -> None:
        preview = self._preview
        if (
            preview is None
            or preview.additions > 0
            or preview.wordlist_error is not None
            or preview.prepare_error is not None
        ):
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
        if event.button.id == "btn-refresh":
            self.action_refresh_preview()
        elif event.button.id == "btn-run":
            self.action_run_pull()
        elif event.button.id == "btn-next-step":
            self.action_empty_collect_next()
        elif event.button.id == "btn-extra-words":
            self.action_open_extra_words()
        elif event.button.id == "btn-view-additions":
            self.action_view_additions()
        elif event.button.id == "btn-back":
            self.action_back()

    def action_back(self) -> None:
        self._controller.invalidate_pull_preview()
        self._preview = None
        self.app.pop_screen()
