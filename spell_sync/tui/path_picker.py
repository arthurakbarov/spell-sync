"""Path Input plus a live completion list (shell-style)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from .path_suggester import list_path_completions


class WordlistPathPicker(Vertical):
    """Type a path; matching folders/files appear in the list below.

    - Empty field or ``~/`` lists the home directory.
    - A trailing ``/`` lists that directory without needing a first letter.
    - Enter / click a row fills the input; directories keep a trailing ``/`` so the
      next listing appears immediately.
    """

    DEFAULT_CSS = """
    WordlistPathPicker {
        height: auto;
        width: 100%;
        max-width: 78;
    }

    WordlistPathPicker #wordlist-input {
        margin-bottom: 1;
    }

    WordlistPathPicker #path-complete-status {
        height: auto;
        color: $text-muted;
        margin-bottom: 0;
    }

    WordlistPathPicker #path-complete-list {
        height: 10;
        min-height: 6;
        max-height: 12;
        border: solid $surface-lighten-2;
    }
    """

    class PathChosen(Message):
        """Posted when the user commits a concrete path from the list."""

        def __init__(self, path: str) -> None:
            super().__init__()
            self.path = path

    def __init__(self, *, value: str = "", id: str | None = "wordlist-path-picker") -> None:
        super().__init__(id=id)
        self._initial_value = value
        self._completions: list[str] = []

    def compose(self) -> ComposeResult:
        yield Input(
            placeholder="~/Documents/Spell Sync/wordlist.txt",
            id="wordlist-input",
            value=self._initial_value,
        )
        yield Static(id="path-complete-status")
        yield OptionList(id="path-complete-list")

    def on_mount(self) -> None:
        self.call_after_refresh(self.refresh_completions)

    @property
    def path_value(self) -> str:
        return self.query_one("#wordlist-input", Input).value

    @path_value.setter
    def path_value(self, value: str) -> None:
        inp = self.query_one("#wordlist-input", Input)
        inp.value = value
        inp.cursor_position = len(value)
        self.refresh_completions()

    def focus_input(self) -> None:
        self.query_one("#wordlist-input", Input).focus()

    def refresh_completions(self) -> None:
        if not self.is_mounted:
            return
        typed = self.path_value
        hits = list_path_completions(typed)
        self._completions = [hit.value for hit in hits]
        status = self.query_one("#path-complete-status", Static)
        option_list = self.query_one("#path-complete-list", OptionList)
        option_list.clear_options()
        if not hits:
            if not typed.strip():
                status.update("Matches under home (~/). Type / after a folder to list it.")
            else:
                status.update("No matches in this folder.")
            return
        label = "home" if not typed.strip() or typed.strip() in {"~", "~/"} else "folder"
        status.update(f"{len(hits)} match(es) in this {label} — ↑↓ then Enter, or click")
        option_list.add_options(
            [Option(hit.prompt, id=f"path-{index}") for index, hit in enumerate(hits)]
        )
        if option_list.option_count:
            option_list.highlighted = 0

    def apply_highlighted(self) -> bool:
        """Apply the highlighted list row into the input. Returns True if applied."""
        option_list = self.query_one("#path-complete-list", OptionList)
        index = option_list.highlighted
        if index is None or index < 0 or index >= len(self._completions):
            if len(self._completions) == 1:
                index = 0
            else:
                return False
        self._apply_value(self._completions[index])
        return True

    def _apply_value(self, value: str) -> None:
        self.path_value = value
        self.focus_input()
        self.post_message(self.PathChosen(value))

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "wordlist-input":
            return
        self.refresh_completions()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        index = event.option_index
        if 0 <= index < len(self._completions):
            self._apply_value(self._completions[index])
