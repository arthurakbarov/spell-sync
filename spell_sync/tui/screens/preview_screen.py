"""Read-only push preview with continue-to-push."""

from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Static
from textual.worker import WorkerState

from ...application.product_concepts import (
    CONTINUE_TO_UPDATE_APPS_LABEL,
    DICTIONARY_TABLE_COLUMN,
    UPDATE_APPS_LABEL,
    push_preview_unavailable_message,
)
from ...application.push_preview_copy import (
    format_push_preview_summary,
    push_detail_buttons_visible,
)
from ...application.reports import PushPreview
from ...exit_codes import ExitCode
from ..controller import TuiController
from ..layout import action_bar, loading_message, sync_data_table_rows
from ..operational import OPERATIONAL_EXCEPTIONS
from ..workers import LoadTokenMixin


class PreviewScreen(LoadTokenMixin, Screen[None]):
    BINDINGS = [
        ("escape", "back", "Back"),
        ("r", "refresh_preview", "Refresh"),
        ("v", "view_removals", "View removals"),
        ("a", "view_additions", "View additions"),
    ]

    def __init__(
        self,
        controller: TuiController,
        *,
        refresh_on_mount: bool = False,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._preview: PushPreview | None = None
        self._active_token = 0
        self._refresh_on_mount = refresh_on_mount
        self._starting = False
        self._worker: Any = None

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="screen-body", classes="screen-body"):
            yield Static(id="preview-content", classes="screen-prose")
            yield DataTable(id="preview-table")
            yield action_bar(
                Button(
                    CONTINUE_TO_UPDATE_APPS_LABEL,
                    id="btn-continue-push",
                    variant="primary",
                ),
                Button("View removals", id="btn-view-removals"),
                Button("View additions", id="btn-view-additions"),
                Button("Refresh preview", id="btn-refresh-preview"),
                Button("Back", id="btn-back"),
            )
        yield Footer()

    def on_mount(self) -> None:
        if self._refresh_on_mount:
            self.refresh_preview()
            return
        try:
            self._render_preview(self._controller.preview())
        except OPERATIONAL_EXCEPTIONS:
            self.query_one("#preview-content", Static).update("× Preview load failed.")

    def _set_loading(self, loading: bool) -> None:
        self.query_one("#btn-refresh-preview", Button).disabled = loading
        self.query_one("#btn-view-removals", Button).disabled = loading
        self.query_one("#btn-view-additions", Button).disabled = loading
        self.query_one("#btn-continue-push", Button).disabled = loading

    def _sync_delta_buttons(self, preview: PushPreview | None) -> None:
        add_btn = self.query_one("#btn-view-additions", Button)
        rem_btn = self.query_one("#btn-view-removals", Button)
        if (
            preview is None
            or preview.wordlist_error is not None
            or preview.prepare_error is not None
        ):
            add_btn.display = False
            rem_btn.display = False
            return
        has_additions, has_removals = push_detail_buttons_visible(preview)
        add_btn.display = has_additions
        rem_btn.display = has_removals

    def _update_continue_button(self, preview: PushPreview) -> None:
        btn = self.query_one("#btn-continue-push", Button)
        back = self.query_one("#btn-back", Button)
        has_work = (
            preview.is_executable
            and preview.prepared is not None
            and preview.targets_to_update > 0
            and not self._controller.mutation_active
            and not self._starting
        )
        btn.display = has_work
        btn.disabled = not has_work
        if has_work:
            btn.label = CONTINUE_TO_UPDATE_APPS_LABEL
            btn.variant = "primary"
            back.variant = "default"
        else:
            btn.label = f"{UPDATE_APPS_LABEL} unavailable"
            btn.variant = "default"
            back.variant = "primary"

    def _render_preview(self, preview: PushPreview) -> None:
        self._preview = preview
        table = self.query_one("#preview-table", DataTable)
        table.clear(columns=True)
        table.add_columns(DICTIONARY_TABLE_COLUMN, "Add", "Remove", "Status")
        for target in preview.targets:
            table.add_row(
                target.name,
                str(target.additions),
                str(target.removals),
                target.status,
            )

        summary = self.query_one("#preview-content", Static)
        if preview.wordlist_error is not None or preview.prepare_error is not None:
            summary.update(push_preview_unavailable_message())
            self._sync_delta_buttons(preview)
            self._update_continue_button(preview)
            sync_data_table_rows(table)
            return

        summary.update(format_push_preview_summary(preview))
        self._sync_delta_buttons(preview)
        self._update_continue_button(preview)
        sync_data_table_rows(table)

    def refresh_preview(self) -> None:
        self._controller.invalidate_push_preview()
        self._preview = None
        self._active_token = self._begin_load()
        self._set_loading(True)
        self.query_one("#preview-content", Static).update(
            loading_message("Loading preview...", "push_preview")
        )
        self._worker = self.load_preview_worker()
        self.set_interval(0.05, self._poll_preview_worker, repeat=40)

    @work(thread=True, exclusive=True, group="preview-load")
    def load_preview_worker(self) -> PushPreview:
        try:
            return self._controller.preview()
        except OPERATIONAL_EXCEPTIONS:
            return PushPreview.unavailable(
                plan_identifier="error",
                prepare_error=ExitCode.PUSH_ABORT,
            )

    def _poll_preview_worker(self) -> None:
        worker = getattr(self, "_worker", None)
        if worker is None or not self.is_mounted:
            return
        if worker.state is WorkerState.ERROR:
            self._set_loading(False)
            self.query_one("#preview-content", Static).update(
                "× Preview unavailable — try Refresh."
            )
            table = self.query_one("#preview-table", DataTable)
            table.clear(columns=True)
            sync_data_table_rows(table)
            self._worker = None
            return
        if worker.state is WorkerState.SUCCESS:
            self._set_loading(False)
            if self._active_token == self._load_generation:
                self._render_preview(worker.result)
            self._worker = None

    def on_load_preview_worker_state_changed(self, event) -> None:
        if event.state is WorkerState.RUNNING:
            return
        self._set_loading(False)
        if event.state is WorkerState.ERROR:
            if self.is_mounted:
                self.query_one("#preview-content", Static).update(
                    "× Preview unavailable — try Refresh."
                )
            return
        if event.state is not WorkerState.SUCCESS:
            return
        if self._active_token != self._load_generation:
            return
        self._render_preview(event.worker.result)
        self._worker = None

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

    def action_continue_push(self) -> None:
        preview = self._preview
        if (
            preview is None
            or not preview.is_executable
            or preview.prepared is None
            or self._controller.mutation_active
            or self._starting
        ):
            self.notify(
                f"{UPDATE_APPS_LABEL} is not available for this preview.",
                severity="warning",
            )
            return
        self._starting = True
        self._update_continue_button(preview)

        def _after_confirm(confirmed: bool | None) -> None:
            self._starting = False
            if not self.is_mounted:
                return
            self._update_continue_button(preview)
            if not confirmed:
                return
            from .operation_screen import OperationScreen

            self.app.push_screen(
                OperationScreen(
                    self._controller,
                    operation="push",
                    push_preview=preview,
                )
            )

        from .push_confirm_screen import PushConfirmScreen

        self.app.push_screen(PushConfirmScreen(self._controller, preview), _after_confirm)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-view-removals":
            self.action_view_removals()
        elif event.button.id == "btn-view-additions":
            self.action_view_additions()
        elif event.button.id == "btn-refresh-preview":
            self.action_refresh_preview()
        elif event.button.id == "btn-continue-push":
            self.action_continue_push()
        elif event.button.id == "btn-back":
            self.action_back()

    def action_refresh_preview(self) -> None:
        self.refresh_preview()

    def action_back(self) -> None:
        self._controller.invalidate_push_preview()
        self._preview = None
        self.app.pop_screen()
