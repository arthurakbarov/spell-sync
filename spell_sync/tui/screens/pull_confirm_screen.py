"""Pull confirmation modal."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Static

from ...application.product_concepts import PULL_PREVIEW_SAFETY
from ...application.reports import PullPreview
from ..controller import TuiController
from ..layout import action_bar


class PullConfirmScreen(ModalScreen[bool]):
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, controller: TuiController, preview: PullPreview) -> None:
        super().__init__()
        self._controller = controller
        self._preview = preview

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="confirm-body", classes="screen-body confirm-body"):
            yield Static(id="confirm-summary")
        yield action_bar(
            Button("Run pull", id="btn-run", variant="primary"),
            Button("Cancel", id="btn-cancel"),
        )
        yield Footer()

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_mount(self) -> None:
        preview = self._preview
        self.query_one("#confirm-summary", Static).update(
            f"{PULL_PREVIEW_SAFETY}\n\n"
            f"Add {preview.additions} words to your personal word list?\n\n"
            f"Wordlist: {preview.wordlist_path}"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(False)
            return
        if event.button.id == "btn-run":
            active = self._controller.active_pull_preview()
            if active is None or active.plan_identifier != self._preview.plan_identifier:
                self.notify("Preview is no longer valid. Refresh and try again.", severity="error")
                self.dismiss(False)
                return
            self.dismiss(True)
