"""Push confirmation modal with typed confirmation for removals."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Static

from ...application.reports import PushPreview
from ..controller import TuiController


class PushConfirmScreen(ModalScreen[bool]):
    """Return True when the user confirms the current preview."""

    def __init__(self, controller: TuiController, preview: PushPreview) -> None:
        super().__init__()
        self._controller = controller
        self._preview = preview
        self._requires_typed = preview.removals > 0

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="confirm-body"):
            yield Static(id="confirm-summary")
            if self._requires_typed:
                yield Input(placeholder="Type PUSH to continue", id="confirm-input")
            yield Button("Run push", id="btn-run", variant="primary")
            yield Button("View removals", id="btn-view-removals")
            yield Button("Cancel", id="btn-cancel")
        yield Footer()

    def on_mount(self) -> None:
        preview = self._preview
        targets = preview.targets_to_update
        if self._requires_typed:
            text = (
                f"This push will remove {preview.removals} words "
                "from application dictionaries.\n\n"
                "The exact removals shown in the preview will be used.\n"
                "Type PUSH to continue.\n\n"
                f"{preview.additions} additions\n"
                f"{preview.removals} removals\n"
                f"Plan id: {preview.plan_identifier}"
            )
            self.query_one("#btn-run", Button).disabled = True
        else:
            text = (
                f"Push the canonical wordlist to {targets} targets?\n\n"
                f"{preview.additions} additions\n"
                f"{preview.removals} removals\n"
                f"Plan id: {preview.plan_identifier}"
            )
        self.query_one("#confirm-summary", Static).update(text)

    def on_input_changed(self, event: Input.Changed) -> None:
        if not self._requires_typed:
            return
        typed = event.value.strip()
        self.query_one("#btn-run", Button).disabled = typed != "PUSH"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(False)
        elif event.button.id == "btn-view-removals":
            from .removals_screen import RemovalsScreen

            target = self._preview.targets[0] if self._preview.targets else None
            words = target.removal_words if target is not None else frozenset()
            name = target.name if target is not None else "target"
            self.app.push_screen(RemovalsScreen(name, words))
        elif event.button.id == "btn-run":
            if self._requires_typed:
                typed = self.query_one("#confirm-input", Input).value.strip()
                if typed != "PUSH":
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
