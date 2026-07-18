"""Main TUI dashboard."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from ..controller import TuiController

_DISABLED_HINT = "Available in the next implementation phase"


class DashboardScreen(Screen[None]):
    BINDINGS = [
        ("r", "refresh_dashboard", "Refresh"),
        ("p", "open_preview", "Preview"),
        ("s", "open_status", "Status"),
    ]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="narrow-warning")
        yield Static(id="dashboard-summary")
        with Vertical(id="action-grid"):
            yield Button("Status", id="btn-status", variant="primary")
            yield Button("Preview", id="btn-preview")
            yield Button("Pull", id="btn-pull", disabled=True, classes="-disabled-action")
            yield Button("Push", id="btn-push", disabled=True, classes="-disabled-action")
            yield Button("Doctor", id="btn-doctor", disabled=True, classes="-disabled-action")
            yield Button("Recovery", id="btn-recovery", disabled=True, classes="-disabled-action")
            yield Button("Logs", id="btn-logs", disabled=True, classes="-disabled-action")
            yield Button("Quit", id="btn-quit", variant="error")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_layout_warning()
        self.refresh_dashboard()

    def _refresh_layout_warning(self) -> None:
        warning = self.query_one("#narrow-warning", Static)
        if self.app.size.width < 80 or self.app.size.height < 24:
            warning.update("! Warning: terminal is smaller than 80x24 — layout may be cramped.")
        else:
            warning.update("")

    def refresh_dashboard(self) -> None:
        state = self._controller.dashboard()
        snapshot = state.snapshot
        if snapshot.wordlist_error is not None:
            health = "× Error"
        elif not state.config_valid or snapshot.empty_wordlist:
            health = "! Warning"
        else:
            health = "✓ Ready"
        config_label = "✓ Valid" if state.config_valid else "× Invalid"
        summary = self.query_one("#dashboard-summary", Static)
        summary.update(
            "\n".join(
                [
                    "Spell Sync",
                    f"Wordlist: {state.wordlist_path}",
                    f"Config: {config_label} ({state.config_status})",
                    f"Targets detected: {state.targets_detected}",
                    f"Words in wordlist: {snapshot.wordlist_count}",
                    f"Health: {health}",
                ]
            )
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "btn-status":
            self.action_open_status()
        elif button_id == "btn-preview":
            self.action_open_preview()
        elif button_id == "btn-quit":
            self.app.exit(0)
        elif button_id in {
            "btn-pull",
            "btn-push",
            "btn-doctor",
            "btn-recovery",
            "btn-logs",
        }:
            self.notify(_DISABLED_HINT, severity="warning")

    def action_refresh_dashboard(self) -> None:
        self._refresh_layout_warning()
        self.refresh_dashboard()

    def action_open_status(self) -> None:
        from .status_screen import StatusScreen

        self.app.push_screen(StatusScreen(self._controller))

    def action_open_preview(self) -> None:
        from .preview_screen import PreviewScreen

        self.app.push_screen(PreviewScreen(self._controller))
