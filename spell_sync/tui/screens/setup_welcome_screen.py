"""First-run setup wizard screens."""

from __future__ import annotations

from dataclasses import replace

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Static

from ...project_setup.prepare import PreparedProjectSetup
from ..controller import TuiController


class SetupWelcomeScreen(Screen[None]):
    BINDINGS = [("escape", "quit_setup", "Quit")]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="welcome-content")
        yield Button("Set up a project", id="btn-setup", variant="primary")
        yield Button("Open existing project", id="btn-open")
        yield Button("Quit", id="btn-quit")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#welcome-content", Static).update(
            "\n".join(
                [
                    "Welcome to Spell Sync",
                    "",
                    "Spell Sync keeps one canonical wordlist synchronized",
                    "with dictionaries used by your applications.",
                    "",
                    "Pull",
                    "Applications → canonical wordlist",
                    "",
                    "Push",
                    "Canonical wordlist → applications",
                ]
            )
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-setup":
            self.app.push_screen(SetupWordlistScreen(self._controller))
        elif event.button.id == "btn-open":
            self.app.push_screen(SetupOpenProjectScreen(self._controller))
        elif event.button.id in {"btn-quit", None}:
            self.action_quit_setup()

    def action_quit_setup(self) -> None:
        self.app.exit()


class SetupOpenProjectScreen(Screen[None]):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Open existing project\n\nPath to wordlist.txt:")
        yield Input(placeholder="~/spell-words/wordlist.txt", id="wordlist-input")
        yield Button("Continue", id="btn-continue", variant="primary")
        yield Button("Back", id="btn-back")
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
            self._controller.opts = replace(self._controller.opts, wordlist=str(path))
            self.app.pop_screen()
            self.app.pop_screen()
            from .dashboard import DashboardScreen

            self.app.push_screen(DashboardScreen(self._controller))


class SetupWordlistScreen(Screen[None]):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="wordlist-content")
        yield Input(
            placeholder="~/spell-words/wordlist.txt",
            id="wordlist-input",
            value=str(self._controller.setup_wordlist_default()),
        )
        yield Button("Continue", id="btn-continue", variant="primary")
        yield Button("Back", id="btn-back")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#wordlist-content", Static).update("Choose the canonical wordlist")

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
            self.app.push_screen(SetupTargetsScreen(self._controller, detail or ""))


class SetupTargetsScreen(Screen[None]):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, controller: TuiController, wordlist_detail: str) -> None:
        super().__init__()
        self._controller = controller
        self._wordlist_detail = wordlist_detail

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="targets-content")
        yield Button("Continue", id="btn-continue", variant="primary")
        yield Button("Back", id="btn-back")
        yield Footer()

    def on_mount(self) -> None:
        discovery = self._controller.refresh_setup_targets()
        lines = [self._wordlist_detail, "", "Detected application dictionaries", ""]
        for row in discovery.targets:
            mark = "[x]" if row.target_id in self._controller.setup_selected_targets else "[ ]"
            status = row.read_status
            count = f" · {row.word_count} words" if row.word_count is not None else ""
            warning = f"\n    ! {row.warning}" if row.warning else ""
            lines.append(f"{mark} {row.display_name}")
            lines.append(f"    {row.path}")
            lines.append(f"    {status.title()}{count}{warning}")
        self.query_one("#targets-content", Static).update("\n".join(lines))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
            return
        if event.button.id == "btn-continue":
            self.app.push_screen(SetupPreviewScreen(self._controller))


class SetupPreviewScreen(Screen[None]):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller
        self._prepared: PreparedProjectSetup | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="preview-content")
        yield Button("Create project", id="btn-create", variant="primary")
        yield Button("Back", id="btn-back")
        yield Footer()

    def on_mount(self) -> None:
        self._prepared = self._controller.prepare_setup_preview()
        prepared = self._prepared
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
        lines.extend(["", "Enabled targets:"])
        lines.extend(f"  {target}" for target in prepared.enabled_targets)
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
