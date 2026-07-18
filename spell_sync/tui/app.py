"""Textual application entry."""

from __future__ import annotations

from textual.app import App
from textual.binding import Binding

from .controller import TuiController
from .screens.dashboard import DashboardScreen


class SpellSyncApp(App[None]):
    CSS_PATH = "app.tcss"
    TITLE = "Spell Sync"

    BINDINGS = [
        Binding("q", "quit_app", "Quit"),
        Binding("question_mark", "help_panel", "Help"),
    ]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self.controller = controller

    def on_mount(self) -> None:
        self.push_screen(DashboardScreen(self.controller))

    def action_quit_app(self) -> None:
        self.exit()


def run_app(controller: TuiController) -> int:
    app = SpellSyncApp(controller)
    app.run()
    return 0
