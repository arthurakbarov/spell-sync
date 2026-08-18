"""Interactive setup target selection screen."""

from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Footer, Header, Static

from ...application.product_concepts import (
    APPLICATIONS_LABEL,
    APPLICATIONS_SCOPE_LINE,
    SETUP_APPS_GOAL_LINE,
)
from ...guest_messages import EXISTING_WORD_LIST_PREFIX
from ...project_setup.discovery import SetupTarget, format_setup_target_word_meta
from ..controller import TuiController
from ..layout import set_optional_static, targets_inline_actions

_EMPTY_TARGETS = (
    "No application dictionaries found yet.\n"
    "Open an app, add one custom word, then return to this screen."
)


class DictionaryIncludeRowWidget(Vertical):
    """Per-dictionary include row under a multi-dictionary family."""

    can_focus = True

    class Toggled(Message):
        def __init__(self, dictionary_name: str) -> None:
            self.dictionary_name = dictionary_name
            super().__init__()

    def __init__(
        self,
        *,
        family_id: str,
        dictionary_name: str,
        word_count: int,
        included: bool,
        enabled: bool,
    ) -> None:
        safe_id = dictionary_name.replace(":", "-").replace(" ", "_")
        super().__init__(
            id=f"dict-row-{family_id}-{safe_id}",
            classes="setup-target-row setup-dictionary-row",
        )
        self._family_id = family_id
        self._dictionary_name = dictionary_name
        self._checkbox_id = f"dict-checkbox-{family_id}-{safe_id}"
        self._word_count = word_count
        self._included = included
        self._enabled = enabled

    def compose(self) -> ComposeResult:
        label = f"  {self._dictionary_name}  ·  {self._word_count:,} words"
        yield Checkbox(
            label,
            value=self._included,
            id=self._checkbox_id,
            disabled=not self._enabled,
        )

    @on(Checkbox.Changed, "Checkbox")
    def _on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id != self._checkbox_id:
            return
        if not self._enabled:
            with event.checkbox.prevent(Checkbox.Changed):
                event.checkbox.value = self._included
            return
        self.post_message(self.Toggled(self._dictionary_name))

    def key_space(self) -> None:
        if not self._enabled:
            return
        self.post_message(self.Toggled(self._dictionary_name))

    def set_included(self, included: bool) -> None:
        self._included = included
        checkbox = self.query_one(f"#{self._checkbox_id}", Checkbox)
        with checkbox.prevent(Checkbox.Changed):
            checkbox.value = included


class SetupTargetRowWidget(Vertical):
    """One selectable setup target row with keyboard focus."""

    can_focus = True

    class Toggled(Message):
        def __init__(self, target_id: str) -> None:
            self.target_id = target_id
            super().__init__()

    def __init__(
        self,
        target: SetupTarget,
        *,
        selected: bool,
        row_index: int,
    ) -> None:
        super().__init__(id=f"target-row-{target.identifier}", classes="setup-target-row")
        self._target = target
        self._selected = selected
        self._row_index = row_index

    def compose(self) -> ComposeResult:
        # Single-line row: avoids nested prose + full-path dumps that blow 80×24.
        label = self._target.display_name
        meta = self._meta_line()
        if meta:
            label = f"{label}  ·  {meta}"
        yield Checkbox(
            label,
            value=self._selected,
            id=f"target-checkbox-{self._target.identifier}",
            disabled=not self._target.selectable,
        )

    def _meta_line(self) -> str:
        """Short status only — never filesystem paths or summed family totals."""
        status = self._target.status.replace("_", " ").title()
        word_meta = format_setup_target_word_meta(self._target)
        if word_meta is not None:
            status = word_meta
        elif self._target.detected:
            status = "✓ Available" if self._target.available else status
        if not self._target.detected:
            status = "× Not detected"
        if self._target.detail and (
            not self._target.selectable
            or self._target.status in {"corrupt", "unreadable", "unsupported"}
        ):
            if self._target.status in {"corrupt", "unreadable", "unsupported"}:
                prefix = "! "
            else:
                prefix = "· "
            detail = self._target.detail
            if len(detail) > 28:
                detail = detail[:27] + "..."
            status = f"{status} {prefix}{detail}".strip()
        return status

    @on(Checkbox.Changed, "Checkbox")
    def _on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id != f"target-checkbox-{self._target.identifier}":
            return
        if not self._target.selectable:
            with event.checkbox.prevent(Checkbox.Changed):
                event.checkbox.value = self._selected
            return
        self.post_message(self.Toggled(self._target.identifier))

    def key_space(self) -> None:
        if not self._target.selectable:
            return
        self.post_message(self.Toggled(self._target.identifier))

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        checkbox = self.query_one(f"#target-checkbox-{self._target.identifier}", Checkbox)
        # Programmatic sync must not re-fire Changed → Toggled (would undo Select/Clear).
        with checkbox.prevent(Checkbox.Changed):
            checkbox.value = selected


TargetRow = SetupTargetRowWidget | DictionaryIncludeRowWidget


def roving_focus_target(rows: list[TargetRow], focused: object, *, step: int) -> TargetRow | None:
    """Return the row `step` positions away from `focused`, wrapping at the ends.

    Shared by the setup and post-setup target screens, which both cycle focus
    through a `#targets-list` of rows with identical wrap-around semantics.
    `step` is `+1` for "next" and `-1` for "previous".
    """
    if not rows:
        return None
    if focused is None or focused not in rows:
        return rows[-1] if step < 0 else rows[0]
    index = rows.index(focused)  # type: ignore[arg-type]  # focused: Widget, rows: TargetRow
    return rows[(index + step) % len(rows)]


class SetupTargetsScreen(Screen[None]):
    BINDINGS = [
        ("escape", "back", "Back"),
        Binding("up", "focus_previous", "Up", show=False),
        Binding("down", "focus_next", "Down", show=False),
        Binding("space", "toggle_focused", "Toggle", show=False),
    ]

    def __init__(self, controller: TuiController, wordlist_detail: str) -> None:
        super().__init__()
        self._controller = controller
        self._wordlist_detail = wordlist_detail

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="screen-body", classes="screen-body targets-setup-body"):
            yield Static(id="targets-header", classes="targets-setup-header")
            yield Vertical(id="targets-list", classes="targets-setup-list")
            yield targets_inline_actions(primary_label="Continue", primary_id="btn-continue")
        yield Footer()

    def on_mount(self) -> None:
        self._render_targets()

    def _selection_status(self) -> str:
        selection = self._controller.setup_selection()
        discovery = self._controller.setup_target_discovery()
        selectable = sum(1 for target in discovery.targets if target.selectable)
        selected = sum(
            1
            for target in discovery.targets
            if target.selectable and target.identifier in selection.selected_target_ids
        )
        return f"{selected}/{selectable} selected · ↑↓ Space"

    def _sync_checkboxes(self) -> None:
        # Family/dictionary layout can change when a family is toggled — rebuild.
        self._render_targets()

    def _render_targets(self) -> None:
        # remove_children/mount are async; schedule exclusive rebuild to avoid DuplicateIds.
        self._rebuild_target_rows()

    def _build_target_widgets(self):
        discovery = self._controller.setup_target_discovery()
        selection = self._controller.setup_selection()
        widgets: list[SetupTargetRowWidget | DictionaryIncludeRowWidget] = []
        for index, target in enumerate(discovery.targets):
            family_on = target.identifier in selection.selected_target_ids
            widgets.append(
                SetupTargetRowWidget(
                    target,
                    selected=family_on,
                    row_index=index,
                )
            )
            if len(target.dictionary_word_counts) > 1:
                for name, count in target.dictionary_word_counts:
                    widgets.append(
                        DictionaryIncludeRowWidget(
                            family_id=target.identifier,
                            dictionary_name=name,
                            word_count=count,
                            included=name not in selection.excluded_dictionary_names,
                            enabled=family_on and target.selectable,
                        )
                    )
        return widgets

    def _compact_header(self) -> str:
        """Two short lines — long path dumps and scope essays zero-height the list."""
        text = (self._wordlist_detail or "").strip()
        lines = text.splitlines()
        project = ""
        words = ""
        has_config = False
        for index, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("Project directory:") and index + 1 < len(lines):
                nxt = lines[index + 1].strip()
                if nxt:
                    project = Path(nxt).name
            elif stripped.startswith(EXISTING_WORD_LIST_PREFIX):
                words = stripped.removeprefix(EXISTING_WORD_LIST_PREFIX).strip()
            elif stripped.startswith("Existing config detected"):
                has_config = True
        parts: list[str] = []
        if project:
            parts.append(project)
        if words:
            parts.append(words)
        if has_config:
            parts.append("existing config")
        summary = " · ".join(parts) if parts else "Choose apps"
        return f"{APPLICATIONS_LABEL}\n{summary}\n{SETUP_APPS_GOAL_LINE}\n{APPLICATIONS_SCOPE_LINE}"

    @work(exclusive=True, group="setup-targets-render")
    async def _rebuild_target_rows(self) -> None:
        self.query_one("#targets-header", Static).update(self._compact_header())
        container = self.query_one("#targets-list", Vertical)
        await container.remove_children()
        rows = self._build_target_widgets()
        if rows:
            await container.mount(*rows)
        else:
            await container.mount(Static(_EMPTY_TARGETS, classes="setup-targets-empty"))
        if self.is_mounted:
            set_optional_static(
                self.query_one("#targets-status", Static),
                self._selection_status(),
            )

    @on(SetupTargetRowWidget.Toggled)
    def _on_target_toggled(self, event: SetupTargetRowWidget.Toggled) -> None:
        previous = event.target_id in self._controller.setup_selection().selected_target_ids
        if not self._controller.toggle_setup_target(event.target_id):
            row = self.query_one(f"#target-row-{event.target_id}", SetupTargetRowWidget)
            row.set_selected(previous)
            return
        self._render_targets()

    @on(DictionaryIncludeRowWidget.Toggled)
    def _on_dictionary_toggled(self, event: DictionaryIncludeRowWidget.Toggled) -> None:
        if not self._controller.toggle_setup_dictionary(event.dictionary_name):
            self._render_targets()
            return
        self._render_targets()

    def _focusable_rows(self) -> list[TargetRow]:
        container = self.query_one("#targets-list", Vertical)
        return [
            child
            for child in container.children
            if isinstance(child, (SetupTargetRowWidget, DictionaryIncludeRowWidget))
        ]

    def action_focus_previous(self) -> None:
        target = roving_focus_target(self._focusable_rows(), self.focused, step=-1)
        if target is not None:
            target.focus()

    def action_focus_next(self) -> None:
        target = roving_focus_target(self._focusable_rows(), self.focused, step=1)
        if target is not None:
            target.focus()

    def action_toggle_focused(self) -> None:
        focused = self.focused
        if isinstance(focused, SetupTargetRowWidget) and focused._target.selectable:
            focused.post_message(SetupTargetRowWidget.Toggled(focused._target.identifier))
        elif isinstance(focused, DictionaryIncludeRowWidget) and focused._enabled:
            focused.post_message(DictionaryIncludeRowWidget.Toggled(focused._dictionary_name))

    def action_back(self) -> None:
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_back()
            return
        if event.button.id == "btn-select-available":
            self._controller.select_available_setup_targets()
            self._sync_checkboxes()
            return
        if event.button.id == "btn-clear":
            self._controller.clear_setup_target_selection()
            self._sync_checkboxes()
            return
        if event.button.id == "btn-continue":
            from .setup_welcome_screen import SetupPreviewScreen

            self.app.push_screen(SetupPreviewScreen(self._controller))
