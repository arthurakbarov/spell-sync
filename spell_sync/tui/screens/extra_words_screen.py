"""Review extra words: keep a subset, then remove the rest from apps."""

from textual import on, work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Static
from textual.worker import WorkerState

from ...application.extra_words import ExtraWordInventory, ExtraWordRow
from ...application.product_concepts import (
    CONTINUE_TO_UPDATE_APPS_LABEL,
    EXTRA_WORDS_ADD_LABEL,
    EXTRA_WORDS_ADDED,
    EXTRA_WORDS_CONTINUE_TO_REMOVE_LABEL,
    EXTRA_WORDS_DONE_HINT,
    EXTRA_WORDS_EMPTY,
    EXTRA_WORDS_FIND_LABEL,
    EXTRA_WORDS_HEADING,
    EXTRA_WORDS_KEEP_HINT,
    EXTRA_WORDS_REMAINING_EMPTY,
    EXTRA_WORDS_REMOVE_LABEL,
    EXTRA_WORDS_SKIP_TO_REMOVE_LABEL,
    EXTRA_WORDS_TOGGLE_ALL_LABEL,
    EXTRA_WORDS_UNAVAILABLE,
    EXTRA_WORDS_WIPE_CONFLICT,
    EXTRA_WORDS_WIPE_DONE,
    EXTRA_WORDS_WIPE_EMPTY,
    EXTRA_WORDS_WIPE_HEADING,
    EXTRA_WORDS_WIPE_HINT,
    EXTRA_WORDS_WIPE_WRITE_FAILED,
    EXTRA_WORDS_WRITE_BLOCKED,
    extra_words_page_line,
)
from ...application.wordlist_edit import AppendWordsResult
from ..context_next import continue_to_update_apps, wordlist_ready_for_update
from ..controller import TuiController
from ..layout import action_bar, loading_message, set_optional_static, sync_data_table_rows
from ..operational import OPERATIONAL_EXCEPTIONS
from ..workers import LoadTokenMixin

EXTRA_WORDS_PAGE_SIZE = 8
_PHASE_KEEP = "keep"
_PHASE_WIPE = "wipe"
_PHASE_DONE = "done"


class ExtraWordsScreen(LoadTokenMixin, Screen[None]):
    BINDINGS = [
        ("escape", "back", "Back"),
        ("left", "prev_page", "Previous page"),
        ("right", "next_page", "Next page"),
    ]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller
        self._inventory: ExtraWordInventory | None = None
        self._phase = _PHASE_KEEP
        self._selected: set[str] = set()
        self._kept_keys: set[str] = set()
        self._list_changed = False
        self._apps_changed = False
        self._page = 0
        self._active_token = 0
        self._busy = False

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="screen-body", classes="screen-body"):
            yield Static(id="extra-words-heading", classes="screen-prose")
            yield Static(id="extra-words-hint", classes="screen-prose")
            yield Static(id="extra-words-page", classes="screen-prose")
            yield Static(id="extra-words-status", classes="screen-prose")
            yield DataTable(id="extra-words-table", cursor_type="row")
            yield action_bar(
                Button(EXTRA_WORDS_ADD_LABEL, id="btn-add", variant="primary"),
                Button(EXTRA_WORDS_CONTINUE_TO_REMOVE_LABEL, id="btn-skip-remove"),
                Button(EXTRA_WORDS_REMOVE_LABEL, id="btn-remove"),
                Button(CONTINUE_TO_UPDATE_APPS_LABEL, id="btn-continue-update"),
                Button(EXTRA_WORDS_TOGGLE_ALL_LABEL, id="btn-toggle-all"),
                Button(EXTRA_WORDS_FIND_LABEL, id="btn-find"),
                Button("Previous page", id="btn-prev"),
                Button("Next page", id="btn-next"),
                Button("Back", id="btn-back"),
                status_id="extra-words-action-status",
            )
        yield Footer()

    def on_mount(self) -> None:
        set_optional_static(self.query_one("#extra-words-status", Static), "")
        try:
            self._apply_inventory(self._controller.extra_word_inventory())
        except OPERATIONAL_EXCEPTIONS:
            self._render_unavailable()

    def _visible_rows(self) -> tuple[ExtraWordRow, ...]:
        if self._inventory is None:
            return ()
        if self._phase == _PHASE_KEEP:
            return self._inventory.rows
        if self._phase == _PHASE_DONE:
            return ()
        return tuple(
            row for row in self._inventory.rows if row.word.casefold() not in self._kept_keys
        )

    def _page_count(self, rows: tuple[ExtraWordRow, ...]) -> int:
        if not rows:
            return 1
        return (len(rows) + EXTRA_WORDS_PAGE_SIZE - 1) // EXTRA_WORDS_PAGE_SIZE

    def _page_rows(self) -> tuple[ExtraWordRow, ...]:
        rows = self._visible_rows()
        start = self._page * EXTRA_WORDS_PAGE_SIZE
        return rows[start : start + EXTRA_WORDS_PAGE_SIZE]

    def _glyph(self, key: str) -> str:
        return "✓" if key in self._selected else "·"

    def _checkbox_header(self) -> str:
        return "Keep" if self._phase == _PHASE_KEEP else "Remove"

    def _prepare_columns(self, table: DataTable) -> None:
        table.clear(columns=True)
        table.add_column(self._checkbox_header(), key="keep", width=8)
        table.add_column("Word", key="word")
        table.add_column("Sources", key="sources")

    def _render_unavailable(self) -> None:
        self._inventory = None
        self._selected.clear()
        self._page = 0
        set_optional_static(self.query_one("#extra-words-heading", Static), EXTRA_WORDS_HEADING)
        set_optional_static(self.query_one("#extra-words-hint", Static), EXTRA_WORDS_UNAVAILABLE)
        set_optional_static(self.query_one("#extra-words-page", Static), "")
        table = self.query_one("#extra-words-table", DataTable)
        self._prepare_columns(table)
        sync_data_table_rows(table)
        self._sync_actions()

    def _apply_inventory(self, inventory: ExtraWordInventory) -> None:
        self._inventory = inventory
        self._phase = _PHASE_KEEP
        self._kept_keys.clear()
        self._selected.clear()
        self._page = 0
        if not inventory.is_available:
            self._render_unavailable()
            return
        self._render_table()

    def _enter_wipe_phase(self) -> None:
        self._phase = _PHASE_WIPE
        remaining = self._visible_rows()
        if not remaining and self._should_offer_update():
            self._enter_done_phase()
            return
        self._selected = {row.word.casefold() for row in remaining}
        self._page = 0
        self._render_table()

    def _enter_done_phase(self) -> None:
        self._phase = _PHASE_DONE
        self._selected.clear()
        self._page = 0
        self._render_table()

    def _should_offer_update(self) -> bool:
        if not (self._list_changed or self._apps_changed):
            return False
        return wordlist_ready_for_update(self._controller)

    def _render_table(self) -> None:
        if self._phase == _PHASE_DONE:
            set_optional_static(self.query_one("#extra-words-heading", Static), EXTRA_WORDS_HEADING)
            set_optional_static(self.query_one("#extra-words-hint", Static), EXTRA_WORDS_DONE_HINT)
            set_optional_static(self.query_one("#extra-words-page", Static), "")
            table = self.query_one("#extra-words-table", DataTable)
            table.display = False
            table.clear(columns=True)
            self._sync_actions()
            return
        rows = self._visible_rows()
        pages = self._page_count(rows)
        if self._page >= pages:
            self._page = max(0, pages - 1)
        if self._phase == _PHASE_KEEP:
            heading = EXTRA_WORDS_HEADING
            hint = EXTRA_WORDS_KEEP_HINT if rows else EXTRA_WORDS_EMPTY
        else:
            heading = EXTRA_WORDS_WIPE_HEADING
            hint = EXTRA_WORDS_WIPE_HINT if rows else EXTRA_WORDS_REMAINING_EMPTY
        set_optional_static(self.query_one("#extra-words-heading", Static), heading)
        set_optional_static(self.query_one("#extra-words-hint", Static), hint)
        if rows:
            set_optional_static(
                self.query_one("#extra-words-page", Static),
                extra_words_page_line(self._page + 1, pages, len(rows)),
            )
        else:
            set_optional_static(self.query_one("#extra-words-page", Static), "")
        table = self.query_one("#extra-words-table", DataTable)
        table.display = True
        self._prepare_columns(table)
        for row in self._page_rows():
            key = row.word.casefold()
            table.add_row(self._glyph(key), row.word, ", ".join(row.sources), key=key)
        sync_data_table_rows(table)
        self._sync_actions()

    def _sync_actions(self) -> None:
        done = self._phase == _PHASE_DONE
        add_btn = self.query_one("#btn-add", Button)
        skip_btn = self.query_one("#btn-skip-remove", Button)
        remove_btn = self.query_one("#btn-remove", Button)
        continue_btn = self.query_one("#btn-continue-update", Button)
        toggle_btn = self.query_one("#btn-toggle-all", Button)
        find_btn = self.query_one("#btn-find", Button)
        prev_btn = self.query_one("#btn-prev", Button)
        next_btn = self.query_one("#btn-next", Button)
        back_btn = self.query_one("#btn-back", Button)

        continue_btn.display = done
        continue_btn.disabled = self._busy
        continue_btn.variant = "primary" if done else "default"
        if done:
            add_btn.display = False
            skip_btn.display = False
            remove_btn.display = False
            toggle_btn.display = False
            find_btn.display = False
            prev_btn.display = False
            next_btn.display = False
            back_btn.variant = "default"
            back_btn.disabled = self._busy
            return

        rows = self._visible_rows()
        pages = self._page_count(rows)
        has_rows = bool(rows)
        keep = self._phase == _PHASE_KEEP
        has_keep_selection = keep and bool(self._selected)
        add_btn.display = keep and has_rows and has_keep_selection
        add_btn.disabled = self._busy
        add_btn.variant = "primary" if add_btn.display else "default"

        skip_btn.display = keep and has_rows
        skip_btn.disabled = self._busy
        if has_keep_selection:
            skip_btn.label = EXTRA_WORDS_SKIP_TO_REMOVE_LABEL
            skip_btn.variant = "default"
        else:
            skip_btn.label = EXTRA_WORDS_CONTINUE_TO_REMOVE_LABEL
            skip_btn.variant = "primary"

        remaining_empty = (not keep) and (not has_rows)
        remove_btn.display = (not keep) and not remaining_empty
        remove_btn.disabled = self._busy
        remove_btn.variant = "error" if remove_btn.display else "default"

        toggle_btn.display = has_rows
        toggle_btn.disabled = self._busy
        find_btn.display = keep
        find_btn.disabled = self._busy
        prev_btn.display = has_rows and pages > 1
        prev_btn.disabled = self._busy or self._page <= 0
        next_btn.display = has_rows and pages > 1
        next_btn.disabled = self._busy or self._page >= pages - 1

        if not add_btn.display and not skip_btn.display and not remove_btn.display:
            back_btn.variant = "primary"
        else:
            back_btn.variant = "default"
        back_btn.disabled = self._busy

    def _selected_words(self) -> tuple[str, ...]:
        return tuple(
            row.word for row in self._visible_rows() if row.word.casefold() in self._selected
        )

    def _toggle_key(self, key: str) -> None:
        if key in self._selected:
            self._selected.discard(key)
        else:
            self._selected.add(key)
        table = self.query_one("#extra-words-table", DataTable)
        if key in table.rows:
            table.update_cell(key, "keep", self._glyph(key))
        self._sync_actions()

    def _toggle_all(self) -> None:
        keys = {row.word.casefold() for row in self._visible_rows()}
        if keys and keys <= self._selected:
            self._selected -= keys
        else:
            self._selected |= keys
        self._render_table()

    @on(DataTable.RowSelected, "#extra-words-table")
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key is None or event.row_key.value is None:
            return
        self._toggle_key(str(event.row_key.value))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "btn-back":
            self.action_back()
        elif button_id == "btn-find":
            self._start_scan()
        elif button_id == "btn-toggle-all":
            self._toggle_all()
        elif button_id == "btn-add":
            self._add_selected()
        elif button_id == "btn-skip-remove":
            self._skip_to_wipe()
        elif button_id == "btn-remove":
            self._remove_selected()
        elif button_id == "btn-continue-update":
            continue_to_update_apps(self.app, self._controller, replace_current=True)
        elif button_id == "btn-prev":
            self.action_prev_page()
        elif button_id == "btn-next":
            self.action_next_page()

    def action_back(self) -> None:
        if self._busy:
            return
        self.app.pop_screen()

    def action_prev_page(self) -> None:
        if self._page <= 0:
            return
        self._page -= 1
        self._render_table()

    def action_next_page(self) -> None:
        if self._page + 1 >= self._page_count(self._visible_rows()):
            return
        self._page += 1
        self._render_table()

    def _start_scan(self) -> None:
        self._busy = True
        self._sync_actions()
        set_optional_static(
            self.query_one("#extra-words-heading", Static),
            loading_message("Finding extra words...", "extra_words_scan"),
        )
        self._active_token = self._begin_load()
        self.scan_worker()

    @work(thread=True, exclusive=True, group="extra-words-scan")
    def scan_worker(self) -> ExtraWordInventory | None:
        try:
            return self._controller.extra_word_inventory()
        except OPERATIONAL_EXCEPTIONS:
            return None

    def on_scan_worker_state_changed(self, event) -> None:
        if event.state is WorkerState.RUNNING:
            return
        self._busy = False
        if event.state is WorkerState.ERROR:
            if self._is_current_load(self._active_token):
                self._render_unavailable()
            return
        if event.state is not WorkerState.SUCCESS:
            return
        if not self._is_current_load(self._active_token):
            return
        payload = event.worker.result
        if payload is None:
            self._render_unavailable()
            return
        self._apply_inventory(payload)

    def _add_selected(self) -> None:
        words = self._selected_words()
        if not words:
            return
        try:
            result = self._controller.append_words("\n".join(words))
        except OPERATIONAL_EXCEPTIONS:
            self.notify(EXTRA_WORDS_WRITE_BLOCKED, severity="error")
            return
        if not isinstance(result, AppendWordsResult) or not result.had_usable_input:
            self.notify(EXTRA_WORDS_WRITE_BLOCKED, severity="error")
            return
        self._list_changed = True
        self._kept_keys = set(result.accepted_keys)
        status_lines: list[str] = []
        if result.added_count:
            status_lines.append(EXTRA_WORDS_ADDED)
        status_lines.extend(result.detail_lines())
        set_optional_static(
            self.query_one("#extra-words-status", Static),
            "\n".join(status_lines),
        )
        self._enter_wipe_phase()

    def _skip_to_wipe(self) -> None:
        self._kept_keys = set()
        set_optional_static(self.query_one("#extra-words-status", Static), "")
        self._enter_wipe_phase()

    def _remove_selected(self) -> None:
        if self._inventory is None:
            return
        words = self._selected_words()
        try:
            result = self._controller.subtract_extra_words(self._inventory, words)
        except OPERATIONAL_EXCEPTIONS:
            self.notify(EXTRA_WORDS_WRITE_BLOCKED, severity="error")
            return
        if isinstance(result, int):
            self.notify(EXTRA_WORDS_WRITE_BLOCKED, severity="error")
            return
        if result.conflict:
            self.notify(EXTRA_WORDS_WIPE_CONFLICT, severity="error")
            return
        if result.write_failed:
            self.notify(EXTRA_WORDS_WIPE_WRITE_FAILED, severity="error")
            return
        if not result.ok:
            self.notify(EXTRA_WORDS_WRITE_BLOCKED, severity="error")
            return
        self._apps_changed = bool(result.written)
        self.notify(EXTRA_WORDS_WIPE_DONE if result.written else EXTRA_WORDS_WIPE_EMPTY)
        if self._should_offer_update():
            self._enter_done_phase()
        else:
            self.app.pop_screen()
