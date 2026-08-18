"""Post-setup dictionary target selection and review screens."""

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from ...application.operation_explanations import target_settings_blocker_notice
from ...application.product_concepts import APPLICATIONS_LABEL, APPLICATIONS_SCOPE_LINE
from ...application.user_notices import format_notice_summary
from ...project_setup.discovery import target_display_name
from ...project_setup.target_settings import PreparedTargetSettingsUpdate
from ..controller import TuiController
from ..layout import action_bar, set_optional_static, targets_inline_actions
from .setup_targets_screen import (
    DictionaryIncludeRowWidget,
    SetupTargetRowWidget,
    TargetRow,
    roving_focus_target,
)

_EMPTY_TARGETS = (
    "No application dictionaries found yet.\n"
    "Open an app, add one custom word, then open Applications again."
)


class TargetSettingsScreen(Screen[None]):
    BINDINGS = [
        ("escape", "back", "Back"),
        Binding("up", "focus_previous", "Up", show=False),
        Binding("down", "focus_next", "Down", show=False),
        Binding("space", "toggle_focused", "Toggle", show=False),
        Binding("enter", "open_details", "Details", show=False),
    ]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller
        self._load_error: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="screen-body", classes="screen-body targets-setup-body"):
            yield Static(id="targets-header", classes="targets-setup-header")
            yield Vertical(id="targets-list", classes="targets-setup-list")
            yield targets_inline_actions(
                primary_label="Review changes",
                primary_id="btn-review",
            )
        yield Footer()

    def on_mount(self) -> None:
        snapshot = self._controller.begin_target_settings()
        self._load_error = snapshot.load_error
        self._render_targets()

    def _sync_checkboxes(self) -> None:
        self._render_targets()

    def _render_targets(self) -> None:
        self._rebuild_target_rows()

    def _build_target_widgets(self):
        discovery = self._controller.target_settings_discovery()
        selection = self._controller.target_settings_selection()
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

    @work(exclusive=True, group="target-settings-render")
    async def _rebuild_target_rows(self) -> None:
        header_lines = [
            APPLICATIONS_LABEL,
            "Change which application custom dictionaries Spell Sync uses.",
            APPLICATIONS_SCOPE_LINE,
        ]
        self.query_one("#targets-header", Static).update("\n".join(header_lines))
        # Keep errors in status (header is capped at 3 lines and would clip them).
        status = self.query_one("#targets-status", Static)
        if self._load_error:
            notice = target_settings_blocker_notice(self._load_error)
            if notice is not None:
                set_optional_static(status, f"× {format_notice_summary(notice)}")
            else:
                set_optional_static(status, f"× {self._load_error}")
        else:
            set_optional_static(status, "")
        container = self.query_one("#targets-list", Vertical)
        await container.remove_children()
        rows = self._build_target_widgets()
        if rows:
            await container.mount(*rows)
        else:
            await container.mount(Static(_EMPTY_TARGETS, classes="setup-targets-empty"))
        if self.is_mounted:
            for button in self.query("#btn-review"):
                assert isinstance(button, Button)
                button.disabled = bool(self._load_error)

    @on(SetupTargetRowWidget.Toggled)
    def _on_target_toggled(self, event: SetupTargetRowWidget.Toggled) -> None:
        selection = self._controller.target_settings_selection()
        previous = event.target_id in selection.selected_target_ids
        if not self._controller.toggle_target_settings_target(event.target_id):
            row = self.query_one(f"#target-row-{event.target_id}", SetupTargetRowWidget)
            row.set_selected(previous)
            return
        self._render_targets()

    @on(DictionaryIncludeRowWidget.Toggled)
    def _on_dictionary_toggled(self, event: DictionaryIncludeRowWidget.Toggled) -> None:
        self._controller.toggle_target_settings_dictionary(event.dictionary_name)
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

    def action_open_details(self) -> None:
        focused = self.focused
        if not isinstance(focused, SetupTargetRowWidget):
            return
        from .target_details_screen import TargetDetailsScreen

        self.app.push_screen(TargetDetailsScreen(self._controller, focused._target.identifier))

    def action_back(self) -> None:
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_back()
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


class TargetSettingsReviewScreen(Screen[None]):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller
        self._prepared: PreparedTargetSettingsUpdate | None = None
        self._save_started = False

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="screen-body", classes="screen-body"):
            yield Static(id="review-content", classes="screen-prose")
            yield action_bar(
                Button("Save configuration", id="btn-save", variant="primary"),
                Button("Back", id="btn-back"),
            )
        yield Footer()

    def on_mount(self) -> None:
        self._prepared = self._controller.prepare_target_settings_update()
        self._render_review()

    def on_screen_resume(self) -> None:
        # OperationScreen may refuse to start (mutation held); re-enable Save.
        self._save_started = False
        if self._prepared is not None and self.is_mounted:
            self.query_one("#btn-save", Button).disabled = not self._prepared.can_execute

    def _render_review(self) -> None:
        prepared = self._prepared
        if prepared is None:
            return
        lines = [
            "Review application changes",
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
        newly_excluded = (
            prepared.excluded_dictionary_names - prepared.previous_excluded_dictionary_names
        )
        newly_included = (
            prepared.previous_excluded_dictionary_names - prepared.excluded_dictionary_names
        )
        lines.extend(["", "Exclude dictionaries:"])
        if newly_excluded:
            lines.extend(f"  {name}" for name in sorted(newly_excluded))
        else:
            lines.append("  (none)")
        lines.extend(["", "Include dictionaries:"])
        if newly_included:
            lines.extend(f"  {name}" for name in sorted(newly_included))
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
