"""Pull confirmation modal."""

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Static

from ...application.product_concepts import (
    COLLECT_CONFIRM_BUTTON,
    PULL_PREVIEW_SAFETY,
    collect_confirm_add_line,
)
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
                Button(COLLECT_CONFIRM_BUTTON, id="btn-run", variant="primary"),
                Button("Cancel", id="btn-cancel"),
            )
        yield Footer()

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_mount(self) -> None:
        preview = self._preview
        run_btn = self.query_one("#btn-run", Button)
        cancel_btn = self.query_one("#btn-cancel", Button)
        if preview.additions <= 0:
            self.query_one("#confirm-summary", Static).update(
                f"{PULL_PREVIEW_SAFETY}\n\nNo new words to collect for this preview."
            )
            run_btn.display = False
            run_btn.disabled = True
            cancel_btn.variant = "primary"
            return
        self.query_one("#confirm-summary", Static).update(
            f"{PULL_PREVIEW_SAFETY}\n\n"
            f"{collect_confirm_add_line(preview.additions)}\n\n"
            f"Word list: {preview.wordlist_path}"
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
