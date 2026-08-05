"""Typed confirmation for recovery and discard actions."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Static

from ...application.reports import RecoveryPreview, RecoveryStatus
from ..controller import TuiController
from ..layout import action_bar


class RecoveryConfirmScreen(ModalScreen[bool]):
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(
        self,
        controller: TuiController,
        preview: RecoveryPreview,
        action: str,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._preview = preview
        self._action = action
        self._typed_token = "RECOVER" if action == "recover" else "DISCARD"

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="confirm-body", classes="screen-body confirm-body"):
            yield Static(id="confirm-summary")
            yield Input(
                placeholder=f"Type {self._typed_token} to continue",
                id="confirm-input",
            )
        yield action_bar(
            Button("Run", id="btn-run", variant="primary"),
            Button("Cancel", id="btn-cancel"),
        )
        yield Footer()

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_mount(self) -> None:
        preview = self._preview
        if self._action == "discard":
            text = (
                "Discard recovery metadata\n\n"
                "This does not restore any files.\n"
                "The current filesystem state will be kept.\n"
                "Recovery metadata and snapshots may be removed.\n\n"
                f"Transaction: {preview.transaction_id}\n"
                "Type DISCARD to continue."
            )
        elif (
            preview.status is RecoveryStatus.COMPLETED_CLEANUP_PENDING or self._action == "cleanup"
        ):
            text = (
                "Clean up completed transaction artifacts\n\n"
                "The transaction completed successfully, but recovery artifacts remain.\n"
                "Only cleanup is required.\n\n"
                f"Transaction: {preview.transaction_id}\n"
                "Type RECOVER to continue."
            )
        else:
            text = (
                f"Recover {preview.recoverable_count} file(s)?\n\n"
                f"Conflicts: {preview.conflict_count}\n"
                f"Failures: {preview.failure_count}\n"
                f"Snapshots: {'valid' if preview.snapshots_valid else 'incomplete'}\n"
                f"Transaction: {preview.transaction_id}\n"
                "Type RECOVER to continue."
            )
        self.query_one("#confirm-summary", Static).update(text)
        self.query_one("#btn-run", Button).disabled = True

    def on_input_changed(self, event: Input.Changed) -> None:
        self.query_one("#btn-run", Button).disabled = event.value.strip() != self._typed_token

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(False)
            return
        if event.button.id == "btn-run":
            typed = self.query_one("#confirm-input", Input).value.strip()
            if typed != self._typed_token:
                return
            active = self._controller.active_recovery_preview()
            if active is None or active.preview_fingerprint != self._preview.preview_fingerprint:
                self.notify("Preview is no longer valid. Refresh and try again.", severity="error")
                self.dismiss(False)
                return
            self.dismiss(True)
