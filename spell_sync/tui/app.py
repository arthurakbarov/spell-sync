"""Textual application entry."""

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
        state = self.controller.inspect_project_setup()
        if state.can_start_wizard:
            from .screens.setup_welcome_screen import SetupWelcomeScreen

            self.push_screen(SetupWelcomeScreen(self.controller))
            return
        if state.effective_wordlist is not None:
            self.controller.remember_effective_wordlist(state.effective_wordlist)
        self.push_screen(DashboardScreen(self.controller))

    def action_quit_app(self) -> None:
        if self.controller.mutation_active:
            self.notify(
                "The operation is in progress and must finish or roll back safely.",
                severity="warning",
            )
            return
        self.exit()


def run_app(controller: TuiController) -> int:
    app = SpellSyncApp(controller)
    app.run()
    return 0
