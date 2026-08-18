"""Typed confirmation for recovery and discard actions."""

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Static

from ...application.field_blocks import format_aligned_fields
from ...application.product_concepts import (
    RECOVERY_CLEANUP_REMAINING,
    RECOVERY_FIELD_RECORD,
    recovery_confirm_button,
)
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
        # cleanup uses the same confirm token as recover (body copy says RECOVER).
        self._typed_token = "DISCARD" if action == "discard" else "RECOVER"

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="confirm-body", classes="screen-body confirm-body"):
            yield Static(id="confirm-summary")
            yield Input(
                placeholder=f"Type {self._typed_token} to continue",
                id="confirm-input",
            )
            yield action_bar(
                Button(recovery_confirm_button(self._action), id="btn-run", variant="primary"),
                Button("Cancel", id="btn-cancel"),
            )
        yield Footer()

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_mount(self) -> None:
        preview = self._preview
        if self._action == "discard":
            text = (
                "Discard interrupted-update records\n\n"
                "This does not restore any files.\n"
                "The current files will be kept.\n"
                "Recovery records and snapshots may be removed.\n\n"
                f"{RECOVERY_FIELD_RECORD}: {preview.transaction_id}\n"
                "Type DISCARD to continue."
            )
        elif (
            preview.status is RecoveryStatus.COMPLETED_CLEANUP_PENDING or self._action == "cleanup"
        ):
            text = (
                "Clean up leftover recovery files\n\n"
                f"{RECOVERY_CLEANUP_REMAINING}\n"
                "Only cleanup is required.\n\n"
                f"{RECOVERY_FIELD_RECORD}: {preview.transaction_id}\n"
                "Type RECOVER to continue."
            )
        else:
            fields = "\n".join(
                format_aligned_fields(
                    [
                        ("Conflicts", preview.conflict_count),
                        ("Failures", preview.failure_count),
                        (
                            "Snapshots",
                            "valid" if preview.snapshots_valid else "incomplete",
                        ),
                        (RECOVERY_FIELD_RECORD, preview.transaction_id),
                    ]
                )
            )
            text = (
                f"Recover {preview.recoverable_count} file(s)?\n\n"
                f"{fields}\n"
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
