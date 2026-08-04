"""Read-only push preview with continue-to-push."""

from __future__ import annotations

from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Static
from textual.worker import WorkerState

from ...application.product_concepts import (
    PUSH_DIRECTION_LABEL,
    PUSH_FILTERING_NOTICE,
    PUSH_PREVIEW_SAFETY,
    PUSH_REDUNDANCY_PREVIEW_NOTICE,
    PUSH_SCOPE_NOTICE,
    UPDATE_APPS_LABEL,
)
from ...application.reports import PushPreview
from ..controller import TuiController
from ..workers import LoadTokenMixin


class PreviewScreen(LoadTokenMixin, Screen[None]):
    BINDINGS = [
        ("escape", "back", "Back"),
        ("r", "refresh_preview", "Refresh"),
        ("v", "view_removals", "View removals"),
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
        yield Static(id="preview-content")
        yield DataTable(id="preview-table")
        yield Button("View removals", id="btn-view-removals")
        yield Button("Refresh preview", id="btn-refresh-preview", variant="primary")
        yield Button("Continue to push", id="btn-continue-push")
        yield Footer()

    def on_mount(self) -> None:
        if self._refresh_on_mount:
            self.refresh_preview()
            return
        try:
            self._render_preview(self._controller.preview())
        except Exception:
            self.query_one("#preview-content", Static).update("× Preview load failed.")

    def _set_loading(self, loading: bool) -> None:
        self.query_one("#btn-refresh-preview", Button).disabled = loading
        self.query_one("#btn-view-removals", Button).disabled = loading
        continue_btn = self.query_one("#btn-continue-push", Button)
        if loading:
            continue_btn.disabled = True

    def _update_continue_button(self, preview: PushPreview) -> None:
        btn = self.query_one("#btn-continue-push", Button)
        can_run = (
            preview.is_executable
            and preview.prepared is not None
            and not self._controller.mutation_active
            and not self._starting
        )
        btn.disabled = not can_run
        if can_run:
            btn.label = "Continue to push"
            btn.remove_class("-disabled-action")
        else:
            btn.label = "Push unavailable"
            btn.add_class("-disabled-action")

    def _render_preview(self, preview: PushPreview) -> None:
        self._preview = preview
        table = self.query_one("#preview-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Target", "Add", "Remove", "Status")
        for target in preview.targets:
            table.add_row(
                target.name,
                str(target.additions),
                str(target.removals),
                target.status,
            )

        summary = self.query_one("#preview-content", Static)
        if preview.wordlist_error is not None:
            summary.update(f"× Preview unavailable (exit {int(preview.wordlist_error)})")
            self._update_continue_button(preview)
            return
        if preview.prepare_error is not None:
            summary.update(f"× Plan blocked (exit {int(preview.prepare_error)})")
            self._update_continue_button(preview)
            return

        lines = [
            f"{UPDATE_APPS_LABEL} preview (no writes)",
            "",
            PUSH_PREVIEW_SAFETY,
            "",
            PUSH_DIRECTION_LABEL,
            "",
            f"Created: {preview.created_at}",
            f"Total additions: {preview.additions}",
            f"Total removals: {preview.removals}",
            f"Targets to update: {preview.targets_to_update}",
            f"Unchanged: {preview.unchanged}",
            "",
            PUSH_SCOPE_NOTICE,
            "",
            PUSH_FILTERING_NOTICE,
            "",
            PUSH_REDUNDANCY_PREVIEW_NOTICE,
        ]
        if preview.skipped:
            lines.append(f"Skipped: {', '.join(preview.skipped)}")
        if preview.corrupt:
            lines.append(f"Corrupt: {', '.join(preview.corrupt)}")
        if preview.warnings:
            lines.append(f"Warnings: {'; '.join(preview.warnings)}")
        summary.update("\n".join(lines))
        self._update_continue_button(preview)

    def refresh_preview(self) -> None:
        self._controller.invalidate_push_preview()
        self._preview = None
        self._active_token = self._begin_load()
        self._set_loading(True)
        self.query_one("#preview-content", Static).update("Loading preview...")
        self._worker = self.load_preview_worker()
        self.set_interval(0.05, self._poll_preview_worker, repeat=40)

    @work(thread=True, exclusive=True, group="preview-load")
    def load_preview_worker(self) -> PushPreview:
        try:
            return self._controller.preview()
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

    def _poll_preview_worker(self) -> None:
        worker = getattr(self, "_worker", None)
        if worker is None or not self.is_mounted:
            return
        if worker.state is WorkerState.ERROR:
            self._set_loading(False)
            self.query_one("#preview-content", Static).update(
                "× Preview unavailable — try Refresh."
            )
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

    def _selected_target(self):
        preview = self._preview
        if preview is None or not preview.targets:
            return None
        table = self.query_one("#preview-table", DataTable)
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

    def action_continue_push(self) -> None:
        preview = self._preview
        if (
            preview is None
            or not preview.is_executable
            or preview.prepared is None
            or self._controller.mutation_active
            or self._starting
        ):
            self.notify("Push is not available for this preview.", severity="warning")
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
        elif event.button.id == "btn-refresh-preview":
            self.action_refresh_preview()
        elif event.button.id == "btn-continue-push":
            self.action_continue_push()

    def action_refresh_preview(self) -> None:
        self.refresh_preview()

    def action_back(self) -> None:
        self._controller.invalidate_push_preview()
        self._preview = None
        self.app.pop_screen()
