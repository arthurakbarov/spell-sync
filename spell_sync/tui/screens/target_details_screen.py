"""Target capability details screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from ...application.target_details import format_target_details_text
from ..controller import TuiController


class TargetDetailsScreen(Screen[None]):
    BINDINGS = [
        ("escape", "back", "Back"),
        Binding("b", "back", "Back", show=False),
    ]

    def __init__(self, controller: TuiController, target_id: str) -> None:
        super().__init__()
        self._controller = controller
        self._target_id = target_id

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="target-details-content")
        yield Button("Back", id="btn-back")
        yield Footer()

    def on_mount(self) -> None:
        details = self._controller.target_details(self._target_id)
        content = self.query_one("#target-details-content", Static)
        content.update(format_target_details_text(details))

    def action_back(self) -> None:
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_back()
