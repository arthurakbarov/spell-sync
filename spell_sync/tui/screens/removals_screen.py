"""Scrollable removal word list."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static


class RemovalsScreen(Screen[None]):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, target_name: str, removal_words: frozenset[str]) -> None:
        super().__init__()
        self._target_name = target_name
        self._removal_words = removal_words

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="removals-summary")
        with VerticalScroll(id="removals-scroll"):
            yield Static(id="removals-content")
        yield Footer()

    def on_mount(self) -> None:
        count = len(self._removal_words)
        self.query_one("#removals-summary", Static).update(
            f"Removals for {self._target_name}: {count} word(s)"
        )
        if count:
            body = "\n".join(sorted(self._removal_words))
        else:
            body = "No removals for this target."
        self.query_one("#removals-content", Static).update(body)

    def action_back(self) -> None:
        self.app.pop_screen()
