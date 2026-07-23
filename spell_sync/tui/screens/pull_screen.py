"""Pull preview screen."""

from __future__ import annotations

from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static
from textual.worker import WorkerState

from ...application.product_concepts import (
    PULL_DIRECTION_LABEL,
    PULL_PREVIEW_SAFETY,
    PULL_SCOPE_NOTICE,
    pull_preview_additions_line,
)
from ...application.reports import PullPreview
from ..controller import TuiController
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
        self._worker: Any = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="pull-content")
        yield Button("Refresh preview", id="btn-refresh", variant="primary")
        yield Button("Run pull", id="btn-run")
        yield Button("View additions", id="btn-view-additions")
        yield Footer()

    def on_mount(self) -> None:
        try:
            self._render_preview(self._controller.prepare_pull())
        except Exception:
            self.query_one("#pull-content", Static).update("× Pull preview load failed.")

    def _set_loading(self, loading: bool) -> None:
        self.query_one("#btn-refresh", Button).disabled = loading
        self.query_one("#btn-run", Button).disabled = loading or self._starting

    def _render_preview(self, preview: PullPreview) -> None:
        self._preview = preview
        body = self.query_one("#pull-content", Static)
        run_btn = self.query_one("#btn-run", Button)
        if preview.wordlist_error is not None or preview.prepare_error is not None:
            body.update("× Pull preview unavailable.")
            run_btn.disabled = True
            return
        lines = [
            "Collect words preview (no writes)",
            "",
            PULL_PREVIEW_SAFETY,
            "",
            PULL_DIRECTION_LABEL,
            "",
            pull_preview_additions_line(preview.additions),
            f"Sources ready: {len(preview.sources_used)}",
            f"Sources skipped: {len(preview.sources_skipped)}",
            f"Wordlist: {preview.wordlist_path}",
            f"Plan id: {preview.plan_identifier}",
            f"Created: {preview.created_at}",
            "",
            PULL_SCOPE_NOTICE,
            "",
            "Sources:",
        ]
        for row in preview.source_rows:
            detail = f" ({row.detail})" if row.detail else ""
            lines.append(f"  {row.name}: {row.status}, +{row.words_contributed}{detail}")
        if preview.warnings:
            lines.append("")
            lines.append("Warnings:")
            lines.extend(f"  ! {warning}" for warning in preview.warnings)
        body.update("\n".join(lines))
        run_btn.disabled = not preview.is_executable or self._controller.mutation_active

    def refresh_preview(self) -> None:
        self._controller.invalidate_pull_preview()
        self._preview = None
        self._active_token = self._begin_load()
        self._set_loading(True)
        self.query_one("#pull-content", Static).update("Loading pull preview...")
        self._worker = self.load_pull_worker()
        self.set_interval(0.05, self._poll_pull_worker, repeat=40)

    @work(thread=True, exclusive=True, group="pull-load")
    def load_pull_worker(self) -> PullPreview:
        try:
            return self._controller.prepare_pull()
        except Exception:
            return PullPreview(
                wordlist_path="",
                additions=0,
                before_count=0,
                after_count=0,
                sources_used=(),
                sources_skipped=(),
                source_rows=(),
                warnings=(),
                created_at="",
                plan_identifier="error",
                merged_words=(),
                prepare_error=None,
            )

    def _poll_pull_worker(self) -> None:
        worker = getattr(self, "_worker", None)
        if worker is None or not self.is_mounted:
            return
        if worker.state is WorkerState.ERROR:
            self._set_loading(False)
            self.query_one("#pull-content", Static).update(
                "× Pull preview unavailable — try Refresh."
            )
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
                self.query_one("#pull-content", Static).update(
                    "× Pull preview unavailable — try Refresh."
                )
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
            self.notify("Pull preview is not ready.", severity="warning")
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
        if event.button.id == "btn-refresh":
            self.action_refresh_preview()
        elif event.button.id == "btn-run":
            self.action_run_pull()
        elif event.button.id == "btn-view-additions":
            self.action_view_additions()

    def action_back(self) -> None:
        self._controller.invalidate_pull_preview()
        self._preview = None
        self.app.pop_screen()
