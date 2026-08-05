"""First-run setup wizard screens."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    DirectoryTree,
    Footer,
    Header,
    Input,
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

_STORAGE_RADIO_IDS = {
    "storage-local": STORAGE_STRATEGY_LOCAL,
    "storage-cloud": STORAGE_STRATEGY_CLOUD,
    "storage-git": STORAGE_STRATEGY_GIT,
}

_WORDLIST_NAME = "wordlist.txt"


def _browser_root() -> Path:
    home = Path.home()
    documents = home / "Documents"
    if documents.is_dir():
        return documents
    return home


def filter_wordlist_browser_paths(paths: Iterable[Path]) -> list[Path]:
    """Keep directories and wordlist.txt files; skip other files and OS errors."""
    filtered: list[Path] = []
    for path in paths:
        try:
            if path.is_dir():
                filtered.append(path)
            elif path.is_file() and path.name.lower() == _WORDLIST_NAME:
                filtered.append(path)
        except OSError:
            continue
    return filtered


class WordlistDirectoryTree(DirectoryTree):
    """Show directories and wordlist.txt files only."""

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        return filter_wordlist_browser_paths(paths)


def _action_buttons(*buttons: Button) -> Vertical:
    return Vertical(*buttons, id="setup-actions", classes="setup-actions")


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


class _WordlistBrowseMixin:
    """Shared DirectoryTree + path input behavior for open/repoint screens."""

    def _set_wordlist_input(self, path: Path) -> None:
        self.query_one("#wordlist-input", Input).value = str(path)

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        path = Path(event.path)
        if path.name.lower() == _WORDLIST_NAME:
            self._set_wordlist_input(path)

    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        directory = Path(event.path)
        candidate = directory / _WORDLIST_NAME
        self._set_wordlist_input(candidate)


class SetupOpenProjectScreen(_WordlistBrowseMixin, Screen[None]):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="setup-body", classes="setup-body"):
            yield Static(
                "Open existing word list\n\n"
                "Browse to a folder or select wordlist.txt. "
                "You can still type or paste a path below.",
                classes="setup-prose",
            )
            yield WordlistDirectoryTree(_browser_root(), id="wordlist-browser")
            yield Static("Path to wordlist.txt:", classes="setup-prose")
            yield Input(
                placeholder="~/Documents/Spell Sync/wordlist.txt",
                id="wordlist-input",
            )
        yield _action_buttons(
            Button("Continue", id="btn-continue", variant="primary"),
            Button("Back", id="btn-back"),
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
            return
        if event.button.id == "btn-continue":
            raw = self.query_one("#wordlist-input", Input).value
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


class SetupWordlistScreen(Screen[None]):
    BINDINGS = [("escape", "back", "Back")]

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
            yield Input(
                placeholder="~/Documents/Spell Sync/wordlist.txt",
                id="wordlist-input",
                value=str(self._controller.setup_wordlist_default()),
            )
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
            self.query_one("#wordlist-input", Input).focus()
            return
        if pressed_id.startswith("wordlist-preset-"):
            index = int(pressed_id.rsplit("-", 1)[-1])
            self.query_one("#wordlist-input", Input).value = str(self._presets[index][1])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
            return
        if event.button.id == "btn-continue":
            raw = self.query_one("#wordlist-input", Input).value
            try:
                path, detail = self._controller.validate_setup_wordlist(raw)
            except ValueError as exc:
                self.notify(str(exc), severity="error")
                return
            self._controller.set_setup_wordlist(path)
            from .setup_targets_screen import SetupTargetsScreen

            self.app.push_screen(SetupTargetsScreen(self._controller, detail or ""))


class ChangeWordlistScreen(_WordlistBrowseMixin, Screen[None]):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="setup-body", classes="setup-body"):
            yield Static(
                f"{CHANGE_WORDLIST_HEADING}\n\n{CHANGE_WORDLIST_BODY}\n\n"
                "Browse to a folder or select wordlist.txt, or type a path below.",
                id="change-wordlist-content",
                classes="setup-prose",
            )
            yield WordlistDirectoryTree(_browser_root(), id="wordlist-browser")
            yield Static("Path to wordlist.txt:", classes="setup-prose")
            yield Input(placeholder="~/Documents/Spell Sync/wordlist.txt", id="wordlist-input")
        yield _action_buttons(
            Button("Continue", id="btn-continue", variant="primary"),
            Button("Back", id="btn-back"),
        )
        yield Footer()

    def on_mount(self) -> None:
        wordlist = self._controller.project_wordlist
        if wordlist is not None:
            self.query_one("#wordlist-input", Input).value = str(wordlist)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
            return
        if event.button.id == "btn-continue":
            raw = self.query_one("#wordlist-input", Input).value
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
