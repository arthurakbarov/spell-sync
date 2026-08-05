"""First-run setup wizard screens."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    RadioButton,
    RadioSet,
    Static,
)

from ...application.product_concepts import (
    CHANGE_WORDLIST_BODY,
    CHANGE_WORDLIST_HEADING,
    SETUP_START_BUTTON_LABEL,
    STORAGE_PREVIEW_LABELS,
    STORAGE_SETUP_HEADING,
    STORAGE_SETUP_INTRO,
    STORAGE_STRATEGY_CLOUD,
    STORAGE_STRATEGY_GIT,
    STORAGE_STRATEGY_HINTS,
    STORAGE_STRATEGY_LABELS,
    STORAGE_STRATEGY_LOCAL,
    USER_PROBLEM_STATEMENT,
    WELCOME_BUILT_IN_EXCLUSION,
    WELCOME_INTRO,
    WELCOME_WHAT_YOU_DO,
    WORDLIST_SETUP_HEADING,
    WORDLIST_SETUP_REDUNDANCY_NOTE,
    WORDLIST_SETUP_STORAGE_REMINDER,
    WORDLIST_SETUP_WHAT_BELONGS,
)
from ...project_setup.prepare import PreparedProjectSetup
from ..controller import TuiController
from ..path_picker import WordlistPathPicker

_STORAGE_RADIO_IDS = {
    "storage-local": STORAGE_STRATEGY_LOCAL,
    "storage-cloud": STORAGE_STRATEGY_CLOUD,
    "storage-git": STORAGE_STRATEGY_GIT,
}

_PATH_HINT = (
    "Type a path or pick from the list below. "
    "Empty field lists home (~/). End a folder with / to list everything inside — "
    "no first letter needed. Tab applies the highlighted row."
)


def _action_buttons(*buttons: Button) -> Vertical:
    return Vertical(*buttons, id="setup-actions", classes="setup-actions")


class _PathCompleteMixin:
    """Tab applies the highlighted path-list row."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("tab", "complete_path", "Complete", priority=True),
    ]

    def _path_picker(self) -> WordlistPathPicker:
        return self.query_one(WordlistPathPicker)

    def action_complete_path(self) -> None:
        try:
            picker = self._path_picker()
        except Exception:
            return
        picker.apply_highlighted()


class SetupWelcomeScreen(Screen[None]):
    BINDINGS = [("escape", "quit_setup", "Quit")]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="setup-body", classes="setup-body"):
            yield Static(id="welcome-content", classes="setup-prose")
        yield _action_buttons(
            Button(SETUP_START_BUTTON_LABEL, id="btn-setup", variant="primary"),
            Button("Open existing word list", id="btn-open"),
            Button("Quit", id="btn-quit"),
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#welcome-content", Static).update(
            "\n".join(
                [
                    "Welcome to Spell Sync",
                    "",
                    USER_PROBLEM_STATEMENT,
                    "",
                    WELCOME_INTRO,
                    "",
                    WELCOME_WHAT_YOU_DO,
                    "",
                    WELCOME_BUILT_IN_EXCLUSION,
                ]
            )
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-setup":
            self.app.push_screen(SetupStorageStrategyScreen(self._controller))
        elif event.button.id == "btn-open":
            self.app.push_screen(SetupOpenProjectScreen(self._controller))
        elif event.button.id in {"btn-quit", None}:
            self.action_quit_setup()

    def action_quit_setup(self) -> None:
        self.app.exit()


class SetupStorageStrategyScreen(Screen[None]):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller
        self._selected = STORAGE_STRATEGY_LOCAL

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="setup-body", classes="setup-body"):
            yield Static(id="storage-content", classes="setup-prose")
            with RadioSet(id="storage-strategy"):
                yield RadioButton(
                    STORAGE_STRATEGY_LABELS[STORAGE_STRATEGY_LOCAL],
                    id="storage-local",
                    value=True,
                )
                yield RadioButton(
                    STORAGE_STRATEGY_LABELS[STORAGE_STRATEGY_CLOUD],
                    id="storage-cloud",
                    value=False,
                )
                yield RadioButton(
                    STORAGE_STRATEGY_LABELS[STORAGE_STRATEGY_GIT],
                    id="storage-git",
                    value=False,
                )
            yield Static(id="storage-hint", classes="setup-prose")
        yield _action_buttons(
            Button("Continue", id="btn-continue", variant="primary"),
            Button("Back", id="btn-back"),
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#storage-content", Static).update(
            "\n".join([STORAGE_SETUP_HEADING, "", STORAGE_SETUP_INTRO])
        )
        self._refresh_hint()

    def _refresh_hint(self) -> None:
        self.query_one("#storage-hint", Static).update(
            "\n" + STORAGE_STRATEGY_HINTS[self._selected]
        )

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        pressed_id = event.pressed.id or ""
        strategy = _STORAGE_RADIO_IDS.get(pressed_id)
        if strategy is None:
            return
        self._selected = strategy
        self._refresh_hint()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
            return
        if event.button.id == "btn-continue":
            self._controller.set_setup_storage_strategy(self._selected)
            self.app.push_screen(SetupWordlistScreen(self._controller))

    def action_back(self) -> None:
        self.app.pop_screen()


class SetupOpenProjectScreen(_PathCompleteMixin, Screen[None]):
    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="setup-body", classes="setup-body"):
            yield Static(
                "Open existing word list\n\n" + _PATH_HINT,
                classes="setup-prose",
            )
            yield Static("Path to wordlist.txt:", classes="setup-prose")
            yield WordlistPathPicker()
        yield _action_buttons(
            Button("Continue", id="btn-continue", variant="primary"),
            Button("Back", id="btn-back"),
        )
        yield Footer()

    def on_mount(self) -> None:
        self._path_picker().focus_input()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
            return
        if event.button.id == "btn-continue":
            raw = self._path_picker().path_value
            try:
                path, _detail = self._controller.validate_setup_wordlist(raw)
            except ValueError as exc:
                self.notify(str(exc), severity="error")
                return
            self._controller.set_project_wordlist(path)
            self.app.pop_screen()
            self.app.pop_screen()
            from .dashboard import DashboardScreen

            self.app.push_screen(DashboardScreen(self._controller))

    def action_back(self) -> None:
        self.app.pop_screen()


class SetupWordlistScreen(_PathCompleteMixin, Screen[None]):
    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller
        self._presets = self._controller.setup_wordlist_presets()

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="setup-body", classes="setup-body"):
            yield Static(id="wordlist-content", classes="setup-prose")
            with RadioSet(id="wordlist-preset"):
                for index, (label, _path) in enumerate(self._presets):
                    yield RadioButton(label, id=f"wordlist-preset-{index}", value=(index == 0))
                yield RadioButton("Custom", id="wordlist-preset-custom", value=False)
            yield Static(_PATH_HINT, classes="setup-prose")
            yield WordlistPathPicker(value=str(self._controller.setup_wordlist_default()))
        yield _action_buttons(
            Button("Continue", id="btn-continue", variant="primary"),
            Button("Back", id="btn-back"),
        )
        yield Footer()

    def on_mount(self) -> None:
        strategy = self._controller.setup_storage_strategy()
        hint = (
            STORAGE_STRATEGY_HINTS.get(strategy, "")
            if strategy
            else WORDLIST_SETUP_STORAGE_REMINDER
        )
        lines = [
            WORDLIST_SETUP_HEADING,
            "",
            WORDLIST_SETUP_WHAT_BELONGS,
            "",
            WORDLIST_SETUP_REDUNDANCY_NOTE,
            "",
            WORDLIST_SETUP_STORAGE_REMINDER,
        ]
        if hint and hint != WORDLIST_SETUP_STORAGE_REMINDER:
            lines.extend(["", hint])
        self.query_one("#wordlist-content", Static).update("\n".join(lines))

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        pressed_id = event.pressed.id or ""
        if pressed_id == "wordlist-preset-custom":
            self._path_picker().focus_input()
            return
        if pressed_id.startswith("wordlist-preset-"):
            index = int(pressed_id.rsplit("-", 1)[-1])
            self._path_picker().path_value = str(self._presets[index][1])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
            return
        if event.button.id == "btn-continue":
            raw = self._path_picker().path_value
            try:
                path, detail = self._controller.validate_setup_wordlist(raw)
            except ValueError as exc:
                self.notify(str(exc), severity="error")
                return
            self._controller.set_setup_wordlist(path)
            from .setup_targets_screen import SetupTargetsScreen

            self.app.push_screen(SetupTargetsScreen(self._controller, detail or ""))

    def action_back(self) -> None:
        self.app.pop_screen()


class ChangeWordlistScreen(_PathCompleteMixin, Screen[None]):
    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="setup-body", classes="setup-body"):
            yield Static(
                f"{CHANGE_WORDLIST_HEADING}\n\n{CHANGE_WORDLIST_BODY}\n\n{_PATH_HINT}",
                id="change-wordlist-content",
                classes="setup-prose",
            )
            yield Static("Path to wordlist.txt:", classes="setup-prose")
            yield WordlistPathPicker()
        yield _action_buttons(
            Button("Continue", id="btn-continue", variant="primary"),
            Button("Back", id="btn-back"),
        )
        yield Footer()

    def on_mount(self) -> None:
        wordlist = self._controller.project_wordlist
        picker = self._path_picker()
        if wordlist is not None:
            picker.path_value = str(wordlist)
        picker.focus_input()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
            return
        if event.button.id == "btn-continue":
            raw = self._path_picker().path_value
            try:
                path, _detail = self._controller.validate_setup_wordlist(raw)
            except ValueError as exc:
                self.notify(str(exc), severity="error")
                return
            self._controller.set_project_wordlist(path)
            self.app.pop_screen()
            from .dashboard import DashboardScreen

            dashboard = self.app.screen
            if isinstance(dashboard, DashboardScreen):
                dashboard.refresh_dashboard()

    def action_back(self) -> None:
        self.app.pop_screen()


class SetupPreviewScreen(Screen[None]):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller
        self._prepared: PreparedProjectSetup | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="setup-body", classes="setup-body"):
            yield Static(id="preview-content", classes="setup-prose")
        yield _action_buttons(
            Button("Create project", id="btn-create", variant="primary"),
            Button("Back", id="btn-back"),
        )
        yield Footer()

    def on_mount(self) -> None:
        from ...project_setup.discovery import target_display_name

        self._prepared = self._controller.prepare_setup_preview()
        prepared = self._prepared
        discovery = self._controller.setup_target_discovery()
        selected = set(prepared.selected_target_ids)
        lines = [
            "Create Spell Sync project",
            "",
            f"Project directory:\n  {prepared.project_dir}",
            "",
            "Files to create:",
        ]
        for item in prepared.files:
            if item.action.value == "create":
                lines.append(f"  {item.relative_name}")
            elif item.action.value == "keep":
                lines.append(f"  {item.relative_name} (kept unchanged)")
        strategy = self._controller.setup_storage_strategy()
        if strategy is not None:
            lines.extend(
                [
                    "",
                    "Keeping this list:",
                    f"  {STORAGE_PREVIEW_LABELS.get(strategy, strategy)}",
                ]
            )
        lines.extend(["", "Enabled targets:"])
        enabled_names = [target_display_name(target_id) for target_id in prepared.enabled_targets]
        if enabled_names:
            lines.extend(f"  {name}" for name in enabled_names)
        else:
            lines.append("  (none)")
        not_enabled_names = [
            target.display_name for target in discovery.targets if target.identifier not in selected
        ]
        if not_enabled_names:
            lines.extend(["", "Not enabled:"])
            lines.extend(f"  {name}" for name in not_enabled_names)
        lines.extend(["", "External dictionaries:", "  No changes will be made."])
        self.query_one("#preview-content", Static).update("\n".join(lines))
        self.query_one("#btn-create", Button).disabled = not prepared.can_execute

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
            return
        if event.button.id == "btn-create" and self._prepared is not None:
            from .operation_screen import OperationScreen

            self.app.push_screen(
                OperationScreen(
                    self._controller,
                    operation="setup",
                    setup_prepared=self._prepared,
                )
            )

    def action_back(self) -> None:
        self.app.pop_screen()
