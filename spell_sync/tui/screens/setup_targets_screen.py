"""Interactive setup target selection screen."""

from __future__ import annotations

from typing import Any

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Footer, Header, Static
from textual.worker import Worker, WorkerState

from ...application.product_concepts import TARGETS_SCOPE_NOTICE
from ...project_setup.discovery import SetupTarget
from ..controller import TuiController
from ..workers import LoadTokenMixin


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
        yield Checkbox(
            self._target.display_name,
            value=self._selected,
            id=f"target-checkbox-{self._target.identifier}",
            disabled=not self._target.selectable,
        )
        meta = self._meta_lines()
        if meta:
            yield Static("\n".join(meta), classes="setup-target-meta")

    def _meta_lines(self) -> list[str]:
        lines: list[str] = []
        status = self._target.status.replace("_", " ").title()
        if self._target.word_count is not None:
            status = f"{status} · {self._target.word_count} words"
        elif self._target.detected:
            status = "Available" if self._target.available else status
        if not self._target.detected:
            status = "Not detected"
        lines.append(status)
        if self._target.path is not None:
            lines.append(str(self._target.path))
        if self._target.detail and (
            not self._target.selectable
            or self._target.status in {"corrupt", "unreadable", "unsupported"}
        ):
            prefix = "!" if self._target.status == "corrupt" else "·"
            lines.append(f"{prefix} {self._target.detail}")
        return lines

    def on_focus(self) -> None:
        self.add_class("-focused")

    def on_blur(self) -> None:
        self.remove_class("-focused")

    @on(Checkbox.Changed, "Checkbox")
    def _on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id != f"target-checkbox-{self._target.identifier}":
            return
        if not self._target.selectable:
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
        checkbox.value = selected


class SetupTargetsScreen(LoadTokenMixin, Screen[None]):
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
        self._refresh_token = 0
        self._refresh_worker: Any = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="targets-header")
        yield ScrollableContainer(id="targets-list")
        yield Static(id="targets-status")
        yield Button("Refresh targets", id="btn-refresh")
        yield Button("Select available", id="btn-select-available")
        yield Button("Clear selection", id="btn-clear")
        yield Button("Continue", id="btn-continue", variant="primary")
        yield Button("Back", id="btn-back")
        yield Footer()

    def on_mount(self) -> None:
        self._render_targets()

    def _set_refreshing(self, refreshing: bool) -> None:
        self.query_one("#btn-refresh", Button).disabled = refreshing
        self.query_one("#btn-continue", Button).disabled = refreshing
        self.query_one("#btn-select-available", Button).disabled = refreshing
        self.query_one("#btn-clear", Button).disabled = refreshing
        status = "Refreshing targets…" if refreshing else ""
        self.query_one("#targets-status", Static).update(status)

    def _sync_checkboxes(self) -> None:
        selection = self._controller.setup_selection()
        for target in self._controller.setup_target_discovery().targets:
            row = self.query_one(f"#target-row-{target.identifier}", SetupTargetRowWidget)
            row.set_selected(target.identifier in selection.selected_target_ids)

    def _render_targets(self) -> None:
        discovery = self._controller.setup_target_discovery()
        selection = self._controller.setup_selection()
        header = "\n".join(
            [
                self._wordlist_detail,
                "",
                "Application custom dictionaries",
                "",
                TARGETS_SCOPE_NOTICE,
                "",
                "Use Up/Down and Space to toggle selectable targets.",
            ]
        )
        self.query_one("#targets-header", Static).update(header)
        container = self.query_one("#targets-list", ScrollableContainer)
        container.remove_children()
        for index, target in enumerate(discovery.targets):
            selected = target.identifier in selection.selected_target_ids
            container.mount(
                SetupTargetRowWidget(
                    target,
                    selected=selected,
                    row_index=index,
                )
            )

    @on(SetupTargetRowWidget.Toggled)
    def _on_target_toggled(self, event: SetupTargetRowWidget.Toggled) -> None:
        previous = event.target_id in self._controller.setup_selection().selected_target_ids
        if not self._controller.toggle_setup_target(event.target_id):
            row = self.query_one(f"#target-row-{event.target_id}", SetupTargetRowWidget)
            row.set_selected(previous)
            return
        selected = event.target_id in self._controller.setup_selection().selected_target_ids
        row = self.query_one(f"#target-row-{event.target_id}", SetupTargetRowWidget)
        row.set_selected(selected)

    def action_focus_previous(self) -> None:
        rows = list(self.query(SetupTargetRowWidget))
        if not rows:
            return
        focused = self.focused
        if focused is None or focused not in rows:
            rows[-1].focus()
            return
        index = rows.index(focused)  # type: ignore[arg-type]
        rows[(index - 1) % len(rows)].focus()

    def action_focus_next(self) -> None:
        rows = list(self.query(SetupTargetRowWidget))
        if not rows:
            return
        focused = self.focused
        if focused is None or focused not in rows:
            rows[0].focus()
            return
        index = rows.index(focused)  # type: ignore[arg-type]
        rows[(index + 1) % len(rows)].focus()

    def action_toggle_focused(self) -> None:
        focused = self.focused
        if isinstance(focused, SetupTargetRowWidget) and focused._target.selectable:
            focused.post_message(SetupTargetRowWidget.Toggled(focused._target.identifier))

    def action_back(self) -> None:
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_back()
            return
        if event.button.id == "btn-refresh":
            self._start_refresh()
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

    def _start_refresh(self) -> None:
        if self._refresh_worker is not None and self._refresh_worker.is_running:
            return
        self._refresh_token = self._begin_load()
        self._set_refreshing(True)
        self._refresh_worker = self._refresh_targets_worker(self._refresh_token)

    @work(thread=True, exclusive=True)
    def _refresh_targets_worker(self, token: int) -> int:
        self._controller.refresh_setup_target_discovery()
        return token

    @on(Worker.StateChanged)
    def _on_refresh_worker_state(self, event: Worker.StateChanged) -> None:
        if event.worker != self._refresh_worker:
            return
        if event.state is WorkerState.RUNNING:
            return
        self._set_refreshing(False)
        if event.state is WorkerState.ERROR:
            if self.is_mounted:
                self.query_one("#targets-status", Static).update(
                    "× Target refresh failed — try again."
                )
            self._refresh_worker = None
            return
        if event.state is not WorkerState.SUCCESS:
            return
        token = event.worker.result
        if not isinstance(token, int) or not self._is_current_load(token):
            return
        self._sync_checkboxes()
        self.query_one("#targets-status", Static).update("")
        self._refresh_worker = None
