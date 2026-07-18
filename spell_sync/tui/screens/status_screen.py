"""Read-only status view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from ..controller import TuiController


class StatusScreen(Screen[None]):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="status-content")
        yield Footer()

    def on_mount(self) -> None:
        snapshot = self._controller.status()
        lines = ["Status", ""]
        if snapshot.wordlist_error is not None:
            lines.append(f"× Wordlist error (exit {int(snapshot.wordlist_error)})")
        else:
            lines.append(f"Words in wordlist: {snapshot.wordlist_count}")
            if snapshot.destructive_risk:
                lines.append(f"! {snapshot.destructive_risk}")
            if not snapshot.diffs:
                lines.append("– No dictionary diffs to show.")
            for diff in snapshot.diffs:
                lines.append(
                    f"  {diff.name}: target={diff.target_count} local={diff.local_count} "
                    f"+{diff.to_add} / -{diff.to_remove}"
                )
        self.query_one("#status-content", Static).update("\n".join(lines))

    def action_back(self) -> None:
        self.app.pop_screen()
