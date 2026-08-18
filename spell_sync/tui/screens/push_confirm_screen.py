"""Push confirmation modal with typed confirmation for removals."""

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Static

from ...application.product_concepts import (
    PUSH_PREVIEW_SAFETY,
    UPDATE_CONFIRM_BUTTON,
    UPDATE_REMOVAL_CONFIRM_PROMPT,
    UPDATE_REMOVAL_CONFIRM_TOKEN,
)
from ...application.push_preview_copy import (
    format_additions_confirm_counts,
    format_removals_confirm_counts,
    format_removals_confirm_sentence,
    push_detail_buttons_visible,
)
from ...application.reports import PushPreview
from ..controller import TuiController
from ..layout import action_bar


class PushConfirmScreen(ModalScreen[bool]):
    """Return True when the user confirms the current preview."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, controller: TuiController, preview: PushPreview) -> None:
        super().__init__()
        self._controller = controller
        self._preview = preview
        self._requires_typed = preview.removals > 0

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="confirm-body", classes="screen-body confirm-body"):
            yield Static(id="confirm-summary")
            if self._requires_typed:
                yield Input(
                    placeholder=UPDATE_REMOVAL_CONFIRM_PROMPT,
                    id="confirm-input",
                )
            yield action_bar(
                Button(UPDATE_CONFIRM_BUTTON, id="btn-run", variant="primary"),
                Button("View removals", id="btn-view-removals"),
                Button("View additions", id="btn-view-additions"),
                Button("Cancel", id="btn-cancel"),
            )
        yield Footer()

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_mount(self) -> None:
        preview = self._preview
        targets = preview.targets_to_update
        removal_counts = format_removals_confirm_counts(preview)
        has_additions, has_removals = push_detail_buttons_visible(preview)
        self.query_one("#btn-view-additions", Button).display = has_additions
        self.query_one("#btn-view-removals", Button).display = has_removals
        run_btn = self.query_one("#btn-run", Button)
        cancel_btn = self.query_one("#btn-cancel", Button)
        if targets <= 0:
            text = f"{PUSH_PREVIEW_SAFETY}\n\nNo app dictionaries need an update for this preview."
            run_btn.display = False
            run_btn.disabled = True
            cancel_btn.variant = "primary"
            self.query_one("#confirm-summary", Static).update(text)
            return
        if self._requires_typed:
            text = (
                f"{PUSH_PREVIEW_SAFETY}\n\n"
                f"This update will remove {format_removals_confirm_sentence(preview)} "
                "from application dictionaries.\n\n"
                "The exact removals shown in the preview will be used.\n"
                f"{UPDATE_REMOVAL_CONFIRM_PROMPT}\n\n"
                f"{format_additions_confirm_counts(preview)}\n"
                f"{removal_counts}"
            )
            run_btn.disabled = True
        else:
            text = (
                f"{PUSH_PREVIEW_SAFETY}\n\n"
                f"Update {targets} app dictionaries from your personal word list?\n\n"
                f"{format_additions_confirm_counts(preview)}\n"
                f"{removal_counts}"
            )
        self.query_one("#confirm-summary", Static).update(text)

    def on_input_changed(self, event: Input.Changed) -> None:
        if not self._requires_typed:
            return
        typed = event.value.strip()
        self.query_one("#btn-run", Button).disabled = typed != UPDATE_REMOVAL_CONFIRM_TOKEN

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(False)
        elif event.button.id == "btn-view-removals":
            from .removals_screen import removals_screen_for_push_preview

            self.app.push_screen(removals_screen_for_push_preview(self._preview))
        elif event.button.id == "btn-view-additions":
            from .removals_screen import additions_screen_for_push_preview

            self.app.push_screen(additions_screen_for_push_preview(self._preview))
        elif event.button.id == "btn-run":
            if self._requires_typed:
                typed = self.query_one("#confirm-input", Input).value.strip()
                if typed != UPDATE_REMOVAL_CONFIRM_TOKEN:
                    return
            # Bind confirmation to this preview identity only.
            active = self._controller.active_push_preview()
            if active is None or active.plan_identifier != self._preview.plan_identifier:
                self.notify("Preview is no longer valid. Refresh and try again.", severity="error")
                self.dismiss(False)
                return
            if active.prepared is not self._preview.prepared:
                self.notify("Preview plan changed. Refresh and try again.", severity="error")
                self.dismiss(False)
                return
            self.dismiss(True)
