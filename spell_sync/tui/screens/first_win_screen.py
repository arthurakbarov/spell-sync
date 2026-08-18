"""First-win intent and add-words screens (guest job closure)."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static, TextArea

from ...application.product_concepts import (
    ADD_WORDS_BLOCKED,
    ADD_WORDS_EMPTY_ERROR,
    ADD_WORDS_HEADING,
    ADD_WORDS_INTRO,
    ADD_WORDS_NO_PROJECT,
    ADD_WORDS_NONE_NEW,
    ADD_WORDS_SAVE_LABEL,
    ADD_WORDS_SAVED_NEXT,
    ADD_WORDS_WRITE_FAILED,
    CONTINUE_TO_UPDATE_APPS_LABEL,
    FIRST_WIN_ADD_HINT,
    FIRST_WIN_ADD_LABEL,
    FIRST_WIN_COLLECT_HINT,
    FIRST_WIN_COLLECT_LABEL,
    FIRST_WIN_DASHBOARD_LABEL,
    FIRST_WIN_HEADING,
    FIRST_WIN_INTRO,
    WORD_LIST_UNREADABLE_STATUS,
    added_words_status_block,
)
from ...application.wordlist_edit import AppendWordsResult
from ...io import wordlist_unreadable
from ..context_next import continue_to_update_apps, wordlist_ready_for_update
from ..controller import TuiController
from ..layout import action_bar, menu_item, set_optional_static
from ..operational import OPERATIONAL_EXCEPTIONS


class FirstWinScreen(Screen[None]):
    """Post-setup: choose add words, collect, or dashboard."""

    BINDINGS = [("escape", "go_dashboard", "Dashboard")]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="screen-body", classes="screen-body"):
            yield Static(FIRST_WIN_HEADING, id="first-win-title")
            yield Static(FIRST_WIN_INTRO, id="first-win-intro", classes="screen-prose")
            with Vertical(id="screen-actions", classes="screen-actions"):
                yield menu_item(
                    Button(FIRST_WIN_ADD_LABEL, id="btn-add-words", variant="primary"),
                    FIRST_WIN_ADD_HINT,
                    hint_id="first-win-add-hint",
                )
                yield menu_item(
                    Button(FIRST_WIN_COLLECT_LABEL, id="btn-collect"),
                    FIRST_WIN_COLLECT_HINT,
                    hint_id="first-win-collect-hint",
                )
                yield Button(FIRST_WIN_DASHBOARD_LABEL, id="btn-dashboard")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-add-words":
            self.app.push_screen(AddWordsScreen(self._controller))
        elif event.button.id == "btn-collect":
            from .review_update_screen import ReviewStartScreen

            self._controller.clear_first_run_next_step()
            self.app.push_screen(ReviewStartScreen(self._controller))
        elif event.button.id == "btn-dashboard":
            self.action_go_dashboard()

    def action_go_dashboard(self) -> None:
        self.app.pop_screen()


class AddWordsScreen(Screen[None]):
    """Type personal words into wordlist.txt, then offer Update my apps."""

    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="screen-body", classes="screen-body"):
            yield Static(ADD_WORDS_HEADING, id="add-words-title")
            yield Static(ADD_WORDS_INTRO, id="add-words-intro", classes="screen-prose")
            yield TextArea(id="add-words-input", classes="add-words-input")
            yield Static(id="add-words-status", classes="screen-prose")
            yield action_bar(
                Button(ADD_WORDS_SAVE_LABEL, id="btn-save", variant="primary"),
                Button(CONTINUE_TO_UPDATE_APPS_LABEL, id="btn-update", disabled=True),
                Button("Back", id="btn-back"),
            )
        yield Footer()

    def on_mount(self) -> None:
        set_optional_static(self.query_one("#add-words-status", Static), "")
        self.query_one("#add-words-input", TextArea).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_back()
        elif event.button.id == "btn-save":
            self._save_words()
        elif event.button.id == "btn-update":
            self._open_update()

    def _resolve_wordlist(self) -> Path | None:
        path = self._controller.project_wordlist
        if path is not None:
            return path
        try:
            state = self._controller.dashboard()
            path = Path(state.wordlist_path)
            self._controller.set_project_wordlist(path)
            return path
        except OPERATIONAL_EXCEPTIONS:
            return None

    def _save_words(self) -> None:
        raw = self.query_one("#add-words-input", TextArea).text
        if not raw.strip():
            self.notify(ADD_WORDS_EMPTY_ERROR, severity="error")
            return
        path = self._resolve_wordlist()
        if path is None:
            self.notify(ADD_WORDS_NO_PROJECT, severity="error")
            return
        try:
            result = self._controller.append_words(raw)
        except FileNotFoundError:
            self.notify(ADD_WORDS_NO_PROJECT, severity="error")
            return
        except OSError:
            if wordlist_unreadable(path):
                self.notify(WORD_LIST_UNREADABLE_STATUS, severity="error")
            else:
                self.notify(ADD_WORDS_WRITE_FAILED, severity="error")
            return
        if not isinstance(result, AppendWordsResult):
            self.notify(ADD_WORDS_BLOCKED, severity="error")
            return
        status = self.query_one("#add-words-status", Static)
        update_btn = self.query_one("#btn-update", Button)
        details = result.detail_lines()
        can_update = result.had_usable_input and wordlist_ready_for_update(self._controller)
        if result.added_count == 0:
            set_optional_static(status, "\n".join((ADD_WORDS_NONE_NEW, *details)))
            update_btn.disabled = not can_update
            if result.already_present:
                self._controller.clear_first_run_next_step()
            else:
                self.notify(ADD_WORDS_NONE_NEW, severity="warning")
            return
        lines = [
            ADD_WORDS_SAVED_NEXT,
            "",
            added_words_status_block(result.added),
            *details,
        ]
        set_optional_static(status, "\n".join(lines))
        update_btn.disabled = not can_update
        self._controller.clear_first_run_next_step()
        self.notify(f"Added {result.added_count} word(s).", severity="information")

    def _open_update(self) -> None:
        continue_to_update_apps(self.app, self._controller, replace_current=True)

    def action_back(self) -> None:
        self.app.pop_screen()
