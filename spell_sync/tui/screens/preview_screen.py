"""Read-only push preview."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Static
from textual.worker import WorkerState

from ...application.reports import PushPreview
from ..controller import TuiController
from ..workers import LoadTokenMixin


class PreviewScreen(LoadTokenMixin, Screen[None]):
    BINDINGS = [
        ("escape", "back", "Back"),
        ("r", "refresh_preview", "Refresh"),
        ("v", "view_removals", "View removals"),
    ]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller
        self._preview: PushPreview | None = None
        self._active_token = 0

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="preview-content")
        yield DataTable(id="preview-table")
        yield Button("View removals", id="btn-view-removals")
        yield Button("Refresh preview", id="btn-refresh-preview", variant="primary")
        yield Button(
            "Push execution will be added in Phase 4",
            id="btn-continue-push",
            disabled=True,
            classes="-disabled-action",
        )
        yield Footer()

    def on_mount(self) -> None:
        try:
            self._render_preview(self._controller.preview())
        except Exception:
            self.query_one("#preview-content", Static).update("× Preview load failed.")

    def _set_loading(self, loading: bool) -> None:
        self.query_one("#btn-refresh-preview", Button).disabled = loading
        self.query_one("#btn-view-removals", Button).disabled = loading

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
            return
        if preview.prepare_error is not None:
            summary.update(f"× Plan blocked (exit {int(preview.prepare_error)})")
            return

        lines = [
            "Push preview (no writes)",
            f"Plan id: {preview.plan_identifier}",
            f"Created: {preview.created_at}",
            f"Total additions: {preview.additions}",
            f"Total removals: {preview.removals}",
            f"Targets to update: {preview.targets_to_update}",
            f"Unchanged: {preview.unchanged}",
        ]
        if preview.skipped:
            lines.append(f"Skipped: {', '.join(preview.skipped)}")
        if preview.corrupt:
            lines.append(f"Corrupt: {', '.join(preview.corrupt)}")
        if preview.warnings:
            lines.append(f"Warnings: {'; '.join(preview.warnings)}")
        summary.update("\n".join(lines))

    def refresh_preview(self) -> None:
        self._active_token = self._begin_load()
        self._set_loading(True)
        self.query_one("#preview-content", Static).update("Loading preview...")
        self.load_preview_worker()

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
        if not self._is_current_load(self._active_token):
            return
        self._render_preview(event.worker.result)

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

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-view-removals":
            self.action_view_removals()
        elif event.button.id == "btn-refresh-preview":
            self.action_refresh_preview()

    def action_refresh_preview(self) -> None:
        self._preview = None
        self.refresh_preview()

    def action_back(self) -> None:
        self._preview = None
        self.app.pop_screen()
