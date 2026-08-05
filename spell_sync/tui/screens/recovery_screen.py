"""Recovery inspection and execution entry screen."""

from __future__ import annotations

from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Static
from textual.worker import WorkerState

from ...application.operation_explanations import recovery_blocker_notice
from ...application.reports import RecoveryPreview, RecoveryStatus
from ...application.user_notices import format_notice_block, format_notice_summary
from ..controller import TuiController
from ..layout import action_bar, loading_message
from ..workers import LoadTokenMixin


class RecoveryScreen(LoadTokenMixin, Screen[None]):
    BINDINGS = [
        ("escape", "back", "Back"),
        ("r", "refresh_preview", "Refresh"),
    ]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller
        self._preview: RecoveryPreview | None = None
        self._active_token = 0
        self._starting = False
        self._worker: Any = None

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="screen-body", classes="screen-body"):
            yield Static(id="recovery-content")
            yield DataTable(id="recovery-table")
        yield action_bar(
            Button("Recover", id="btn-recover", variant="primary"),
            Button("View details", id="btn-details"),
            Button("Discard metadata", id="btn-discard"),
            Button("Refresh", id="btn-refresh"),
            Button("Back", id="btn-back"),
        )
        yield Footer()

    def on_mount(self) -> None:
        try:
            self._render_preview(self._controller.inspect_recovery())
        except Exception:
            self.query_one("#recovery-content", Static).update("× Recovery inspection failed.")

    def _set_loading(self, loading: bool) -> None:
        self.query_one("#btn-refresh", Button).disabled = loading
        self.query_one("#btn-recover", Button).disabled = loading or self._starting
        self.query_one("#btn-discard", Button).disabled = loading or self._starting

    def _render_preview(self, preview: RecoveryPreview) -> None:
        self._preview = preview
        self._controller.set_active_recovery_preview(preview)
        table = self.query_one("#recovery-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Item", "Current state", "Recovery action", "Status")
        for item in preview.items:
            table.add_row(
                item.name,
                item.current_state,
                item.recovery_action,
                item.status,
            )

        snapshots = "valid" if preview.snapshots_valid else "incomplete"
        if preview.status is RecoveryStatus.RECOVERY_IN_PROGRESS:
            title = format_notice_summary(
                recovery_blocker_notice(status_value="recovery_in_progress")
            )
        elif preview.status is RecoveryStatus.CORRUPT_JOURNAL:
            title = format_notice_summary(
                recovery_blocker_notice(
                    status_value="corrupt_journal",
                    detail=preview.detail,
                )
            )
        elif preview.status not in {
            RecoveryStatus.ABSENT,
            RecoveryStatus.COMPLETED_CLEANUP_PENDING,
        }:
            title = format_notice_summary(recovery_blocker_notice(status_value="pending_recovery"))
        else:
            title = preview.status.value.replace("_", " ").title()
        lines = [
            title,
            "",
            f"Transaction: {preview.transaction_id or 'n/a'}",
            f"Operation: {preview.command or 'n/a'}",
            f"State: {preview.transaction_state or 'n/a'}",
            f"Started: {preview.started_at or 'n/a'}",
            "",
            f"Recoverable files: {preview.recoverable_count}",
            f"Conflicts: {preview.conflict_count}",
            f"Failures: {preview.failure_count}",
            f"Snapshots: {snapshots}",
        ]
        if preview.detail and preview.status is RecoveryStatus.CORRUPT_JOURNAL:
            notice = recovery_blocker_notice(
                status_value="corrupt_journal",
                detail=preview.detail,
            )
            lines.extend(["", format_notice_block(notice)])
        elif preview.status is RecoveryStatus.RECOVERY_IN_PROGRESS:
            notice = recovery_blocker_notice(status_value="recovery_in_progress")
            lines.extend(["", format_notice_block(notice)])
        elif preview.status is RecoveryStatus.RECOVERABLE:
            notice = recovery_blocker_notice(status_value="pending_recovery")
            lines.extend(["", format_notice_block(notice)])
        if preview.detail and preview.status is not RecoveryStatus.CORRUPT_JOURNAL:
            lines.extend(["", preview.detail])
        if preview.warnings:
            lines.extend(["", "Warnings:"])
            lines.extend(f"  ! {warning}" for warning in preview.warnings)
        self.query_one("#recovery-content", Static).update("\n".join(lines))

        recover_btn = self.query_one("#btn-recover", Button)
        recover_btn.disabled = (
            not (preview.can_recover or preview.can_cleanup) or self._controller.mutation_active
        )
        discard_btn = self.query_one("#btn-discard", Button)
        discard_btn.disabled = not preview.can_discard or self._controller.mutation_active
        if preview.status is RecoveryStatus.ABSENT:
            recover_btn.label = "Recover unavailable"
            discard_btn.label = "Discard unavailable"
        elif preview.status is RecoveryStatus.COMPLETED_CLEANUP_PENDING:
            recover_btn.label = "Clean up artifacts"
            discard_btn.label = "Discard metadata"
        else:
            recover_btn.label = "Recover"
            discard_btn.label = "Discard metadata"

    def refresh_preview(self) -> None:
        self._controller.invalidate_recovery_preview()
        self._preview = None
        self._active_token = self._begin_load()
        self._set_loading(True)
        self.query_one("#recovery-content", Static).update(
            loading_message("Loading recovery preview...", "recovery_preview")
        )
        self._worker = self.load_recovery_worker()
        self.set_interval(0.05, self._poll_recovery_worker, repeat=40)

    @work(thread=True, exclusive=True, group="recovery-load")
    def load_recovery_worker(self) -> RecoveryPreview:
        try:
            return self._controller.inspect_recovery()
        except Exception:
            return RecoveryPreview(
                status=RecoveryStatus.ABSENT,
                transaction_id="",
                command="",
                transaction_state="",
                started_at="",
                wordlist_path="",
                snapshot_directory=None,
                items=(),
                recoverable_count=0,
                conflict_count=0,
                failure_count=0,
                warnings=(),
                can_recover=False,
                can_discard=False,
                snapshots_valid=False,
                preview_fingerprint="error",
                detail="Recovery preview unavailable.",
            )

    def _poll_recovery_worker(self) -> None:
        worker = getattr(self, "_worker", None)
        if worker is None or not self.is_mounted:
            return
        if worker.state is WorkerState.ERROR:
            self._set_loading(False)
            self.query_one("#recovery-content", Static).update(
                "× Recovery preview unavailable — try Refresh."
            )
            self._worker = None
            return
        if worker.state is WorkerState.SUCCESS:
            self._set_loading(False)
            if self._active_token == self._load_generation:
                self._render_preview(worker.result)
            self._worker = None

    def action_refresh_preview(self) -> None:
        self.refresh_preview()

    def action_run_recover(self) -> None:
        preview = self._preview
        if preview is None or not (preview.can_recover or preview.can_cleanup):
            self.notify("Recovery is not available.", severity="warning")
            return
        if self._controller.mutation_active or self._starting:
            self.notify("An operation is already running.", severity="warning")
            return
        self._starting = True
        self.query_one("#btn-recover", Button).disabled = True
        confirm_action = "cleanup" if preview.can_cleanup else "recover"
        operation = confirm_action

        def _after_confirm(confirmed: bool | None) -> None:
            self._starting = False
            if not self.is_mounted:
                return
            self._render_preview(preview)
            if not confirmed:
                return
            from .operation_screen import OperationScreen

            self.app.push_screen(
                OperationScreen(
                    self._controller,
                    operation=operation,
                    recovery_preview=preview,
                )
            )

        from .recovery_confirm_screen import RecoveryConfirmScreen

        self.app.push_screen(
            RecoveryConfirmScreen(self._controller, preview, confirm_action),
            _after_confirm,
        )

    def action_run_discard(self) -> None:
        preview = self._preview
        if preview is None or not preview.can_discard:
            self.notify("Discard is not available.", severity="warning")
            return
        if self._controller.mutation_active or self._starting:
            self.notify("An operation is already running.", severity="warning")
            return
        self._starting = True
        self.query_one("#btn-discard", Button).disabled = True

        def _after_confirm(confirmed: bool | None) -> None:
            self._starting = False
            if not self.is_mounted:
                return
            self._render_preview(preview)
            if not confirmed:
                return
            from .operation_screen import OperationScreen

            self.app.push_screen(
                OperationScreen(
                    self._controller,
                    operation="discard",
                    recovery_preview=preview,
                )
            )

        from .recovery_confirm_screen import RecoveryConfirmScreen

        self.app.push_screen(
            RecoveryConfirmScreen(self._controller, preview, "discard"),
            _after_confirm,
        )

    def action_view_details(self) -> None:
        preview = self._preview
        if preview is None:
            return
        lines = [preview.detail or "", f"Wordlist: {preview.wordlist_path}"]
        if preview.snapshot_directory:
            lines.append(f"Snapshots: {preview.snapshot_directory}")
        for item in preview.items:
            lines.append(
                f"{item.name}: {item.current_state} -> {item.recovery_action} ({item.status})"
            )
        self.notify("\n".join(line for line in lines if line), severity="information")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-refresh":
            self.action_refresh_preview()
        elif event.button.id == "btn-recover":
            self.action_run_recover()
        elif event.button.id == "btn-discard":
            self.action_run_discard()
        elif event.button.id == "btn-details":
            self.action_view_details()
        elif event.button.id == "btn-back":
            self.action_back()

    def action_back(self) -> None:
        self._controller.invalidate_recovery_preview()
        self._preview = None
        self.app.pop_screen()
