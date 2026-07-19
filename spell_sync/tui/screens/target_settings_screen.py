"""Post-setup dictionary target selection and review screens."""

from __future__ import annotations

from typing import Any

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static
from textual.worker import Worker, WorkerState

from ...application.operation_explanations import target_settings_blocker_notice
from ...application.user_notices import format_notice_block, format_notice_summary
from ...project_setup.discovery import target_display_name
from ...project_setup.target_settings import PreparedTargetSettingsUpdate
from ..controller import TuiController
from ..workers import LoadTokenMixin
from .setup_targets_screen import SetupTargetRowWidget


class TargetSettingsScreen(LoadTokenMixin, Screen[None]):
    BINDINGS = [
        ("escape", "back", "Back"),
        Binding("up", "focus_previous", "Up", show=False),
        Binding("down", "focus_next", "Down", show=False),
        Binding("space", "toggle_focused", "Toggle", show=False),
    ]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller
        self._refresh_token = 0
        self._refresh_worker: Any = None
        self._load_error: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="targets-header")
        yield ScrollableContainer(id="targets-list")
        yield Static(id="targets-status")
        yield Button("Refresh", id="btn-refresh")
        yield Button("Select available", id="btn-select-available")
        yield Button("Clear selection", id="btn-clear")
        yield Button("Review changes", id="btn-review", variant="primary")
        yield Button("Back", id="btn-back")
        yield Footer()

    def on_mount(self) -> None:
        snapshot = self._controller.begin_target_settings()
        self._load_error = snapshot.load_error
        self._render_targets()

    def _set_refreshing(self, refreshing: bool) -> None:
        self.query_one("#btn-refresh", Button).disabled = refreshing
        self.query_one("#btn-review", Button).disabled = refreshing or bool(self._load_error)
        self.query_one("#btn-select-available", Button).disabled = refreshing or bool(
            self._load_error
        )
        self.query_one("#btn-clear", Button).disabled = refreshing or bool(self._load_error)
        status = "Refreshing targets…" if refreshing else ""
        self.query_one("#targets-status", Static).update(status)

    def _sync_checkboxes(self) -> None:
        selection = self._controller.target_settings_selection()
        for target in self._controller.target_settings_discovery().targets:
            row = self.query_one(f"#target-row-{target.identifier}", SetupTargetRowWidget)
            row.set_selected(target.identifier in selection.selected_target_ids)

    def _render_targets(self) -> None:
        discovery = self._controller.target_settings_discovery()
        selection = self._controller.target_settings_selection()
        header_lines = [
            "Dictionary targets",
            "",
            "Change which application dictionaries Spell Sync uses.",
            "",
            "Use Up/Down and Space to toggle selectable targets.",
        ]
        if self._load_error:
            notice = target_settings_blocker_notice(self._load_error)
            if notice is not None:
                header_lines.extend(["", f"× {format_notice_summary(notice)}"])
                header_lines.append(format_notice_block(notice))
        self.query_one("#targets-header", Static).update("\n".join(header_lines))
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
        self.query_one("#btn-review", Button).disabled = bool(self._load_error)

    @on(SetupTargetRowWidget.Toggled)
    def _on_target_toggled(self, event: SetupTargetRowWidget.Toggled) -> None:
        selection = self._controller.target_settings_selection()
        previous = event.target_id in selection.selected_target_ids
        if not self._controller.toggle_target_settings_target(event.target_id):
            row = self.query_one(f"#target-row-{event.target_id}", SetupTargetRowWidget)
            row.set_selected(previous)
            return
        selection = self._controller.target_settings_selection()
        selected = event.target_id in selection.selected_target_ids
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
            self._controller.select_available_target_settings()
            self._sync_checkboxes()
            return
        if event.button.id == "btn-clear":
            self._controller.clear_target_settings_selection()
            self._sync_checkboxes()
            return
        if event.button.id == "btn-review":
            self.app.push_screen(TargetSettingsReviewScreen(self._controller))

    def _start_refresh(self) -> None:
        if self._refresh_worker is not None and self._refresh_worker.is_running:
            return
        self._refresh_token = self._begin_load()
        self._set_refreshing(True)
        self._refresh_worker = self._refresh_targets_worker(self._refresh_token)

    @work(thread=True, exclusive=True)
    def _refresh_targets_worker(self, token: int) -> tuple[int, str | None]:
        error = self._controller.refresh_target_settings_discovery()
        return token, error

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
        result = event.worker.result
        if not isinstance(result, tuple) or len(result) != 2:
            return
        token, load_error = result
        if not isinstance(token, int) or not self._is_current_load(token):
            return
        self._load_error = load_error
        if load_error:
            self._render_targets()
        else:
            self._sync_checkboxes()
        self.query_one("#targets-status", Static).update("")
        self._refresh_worker = None


class TargetSettingsReviewScreen(Screen[None]):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller
        self._prepared: PreparedTargetSettingsUpdate | None = None
        self._save_started = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="review-content")
        yield Button("Save configuration", id="btn-save", variant="primary")
        yield Button("Back", id="btn-back")
        yield Footer()

    def on_mount(self) -> None:
        self._prepared = self._controller.prepare_target_settings_update()
        self._render_review()

    def _render_review(self) -> None:
        prepared = self._prepared
        if prepared is None:
            return
        lines = [
            "Review target changes",
            "",
            "Enable:",
        ]
        if prepared.enabled_target_ids:
            lines.extend(
                f"  {target_display_name(target_id)}"
                for target_id in sorted(prepared.enabled_target_ids)
            )
        else:
            lines.append("  (none)")
        lines.extend(["", "Disable:"])
        if prepared.disabled_target_ids:
            lines.extend(
                f"  {target_display_name(target_id)}"
                for target_id in sorted(prepared.disabled_target_ids)
            )
        else:
            lines.append("  (none)")
        lines.extend(
            [
                "",
                "No application dictionaries will be changed.",
            ]
        )
        if prepared.warnings:
            lines.extend(["", "Warnings:"])
            lines.extend(f"  ! {warning}" for warning in prepared.warnings)
        self.query_one("#review-content", Static).update("\n".join(lines))
        self.query_one("#btn-save", Button).disabled = not prepared.can_execute

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
            return
        if event.button.id == "btn-save" and self._prepared is not None:
            if self._save_started:
                return
            self._save_started = True
            from .operation_screen import OperationScreen

            self.app.push_screen(
                OperationScreen(
                    self._controller,
                    operation="targets",
                    target_settings_prepared=self._prepared,
                )
            )

    def action_back(self) -> None:
        self.app.pop_screen()
