"""First-run setup wizard screens."""

from pathlib import Path
from typing import cast

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
    STORAGE_SETUP_LOCAL_PRIMARY,
    STORAGE_SETUP_MORE_INTRO,
    STORAGE_SETUP_MORE_OPTIONS,
    STORAGE_STRATEGY_CLOUD,
    STORAGE_STRATEGY_GIT,
    STORAGE_STRATEGY_HINTS,
    STORAGE_STRATEGY_LABELS,
    STORAGE_STRATEGY_LOCAL,
    USER_PROBLEM_STATEMENT,
    WELCOME_INTRO,
    WELCOME_WHAT_YOU_DO,
    WHY_THIS_IS_SAFE_SHORT,
    WORDLIST_SETUP_CUSTOM_PATH_HINT,
    WORDLIST_SETUP_HEADING,
    WORDLIST_SETUP_RECOMMENDED_BUTTON,
    WORDLIST_SETUP_STORAGE_REMINDER,
    WORDLIST_SETUP_WHAT_BELONGS,
)
from ...project_setup.prepare import PreparedProjectSetup
from ..controller import TuiController
from ..operational import OPERATIONAL_EXCEPTIONS
from ..path_picker import WordlistPathPicker

_STORAGE_RADIO_IDS = {
    "storage-local": STORAGE_STRATEGY_LOCAL,
    "storage-cloud": STORAGE_STRATEGY_CLOUD,
    "storage-git": STORAGE_STRATEGY_GIT,
}

_PATH_HINT = WORDLIST_SETUP_CUSTOM_PATH_HINT


def _action_buttons(*buttons: Button) -> Vertical:
    return Vertical(*buttons, id="setup-actions", classes="setup-actions")


def _home_relative(path: Path) -> str:
    try:
        resolved = path.expanduser().resolve()
        home = Path.home().resolve()
        if resolved == home or home in resolved.parents:
            return "~/" + resolved.relative_to(home).as_posix()
    except OSError, ValueError:
        pass
    return str(path)


class _PathCompleteMixin:
    """Tab applies the highlighted path-list row; Continue commits list→Input."""

    def _path_picker(self) -> WordlistPathPicker:
        screen = cast(Screen[None], self)
        return screen.query_one(WordlistPathPicker)

    def action_complete_path(self) -> None:
        try:
            picker = self._path_picker()
        except OPERATIONAL_EXCEPTIONS:
            return
        picker.apply_highlighted()

    def commit_path_picker_value(
        self,
        *,
        stale_defaults: set[str] | None = None,
        require_wordlist_name: bool = True,
    ) -> str | None:
        """Return the path Continue should use, or None after notifying.

        The completion list only writes into the Input on Enter/click. If the
        user arrows the list and presses Continue, commit the highlight when the
        field is still a directory prefix or a leftover default/prefill.
        """
        screen = cast(Screen[None], self)
        picker = self._path_picker()
        typed = picker.path_value.strip()
        defaults = stale_defaults or set()
        directory_prefix = typed.endswith(("/", "\\")) or typed in {"", "~", "~/"}
        needs_list_commit = directory_prefix or typed in defaults
        if needs_list_commit and not picker.apply_highlighted():
            screen.notify(
                "Select a path from the list (Enter) or type the full path to wordlist.txt.",
                severity="error",
            )
            return None
        raw = picker.path_value.strip()
        if not raw:
            screen.notify("Enter a path to wordlist.txt.", severity="error")
            return None
        if require_wordlist_name and not raw.lower().endswith("wordlist.txt"):
            screen.notify(
                "Choose wordlist.txt (or type its full path), then Continue.",
                severity="error",
            )
            return None
        return raw


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
                    WHY_THIS_IS_SAFE_SHORT,
                ]
            )
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-setup":
            # Default storage: this computer (cloud/Git are later options).
            from ...application.product_concepts import STORAGE_STRATEGY_LOCAL

            self._controller.set_setup_storage_strategy(STORAGE_STRATEGY_LOCAL)
            self.app.push_screen(SetupWordlistScreen(self._controller))
        elif event.button.id == "btn-open":
            self.app.push_screen(SetupOpenProjectScreen(self._controller))
        elif event.button.id in {"btn-quit", None}:
            self.action_quit_setup()

    def action_quit_setup(self) -> None:
        self.app.exit()


class SetupStorageStrategyScreen(Screen[None]):
    """First storage choice: local primary, cloud/Git behind Other options."""

    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="setup-body", classes="setup-body"):
            yield Static(id="storage-content", classes="setup-prose")
            yield Static(id="storage-hint", classes="setup-prose")
            yield _action_buttons(
                Button(STORAGE_SETUP_LOCAL_PRIMARY, id="btn-local", variant="primary"),
                Button(STORAGE_SETUP_MORE_OPTIONS, id="btn-more"),
                Button("Back", id="btn-back"),
            )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#storage-content", Static).update(
            "\n".join([STORAGE_SETUP_HEADING, "", STORAGE_SETUP_INTRO])
        )
        self.query_one("#storage-hint", Static).update(
            STORAGE_STRATEGY_HINTS[STORAGE_STRATEGY_LOCAL]
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
            return
        if event.button.id == "btn-local":
            self._controller.set_setup_storage_strategy(STORAGE_STRATEGY_LOCAL)
            self.app.push_screen(SetupWordlistScreen(self._controller))
            return
        if event.button.id == "btn-more":
            self.app.push_screen(SetupStorageMoreOptionsScreen(self._controller))

    def action_back(self) -> None:
        self.app.pop_screen()


class SetupStorageMoreOptionsScreen(Screen[None]):
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
            "\n".join([STORAGE_SETUP_HEADING, "", STORAGE_SETUP_MORE_INTRO])
        )
        self._refresh_hint()

    def _refresh_hint(self) -> None:
        self.query_one("#storage-hint", Static).update(STORAGE_STRATEGY_HINTS[self._selected])

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
            # Replace more-options + simple storage with wordlist screen.
            self.app.pop_screen()
            self.app.pop_screen()
            self.app.push_screen(SetupWordlistScreen(self._controller))

    def action_back(self) -> None:
        self.app.pop_screen()


class SetupOpenProjectScreen(_PathCompleteMixin, Screen[None]):
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("tab", "complete_path", "Complete", priority=True),
    ]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller
        self._recent = controller.recent_wordlists()

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="setup-body", classes="setup-body"):
            yield Static(
                "Open existing word list\n\n"
                + (
                    "Pick a recent word list, or choose Other path…" if self._recent else _PATH_HINT
                ),
                classes="setup-prose",
            )
            if self._recent:
                yield Static("Recent word lists:", classes="setup-prose")
                with RadioSet(id="recent-wordlist"):
                    for index, path in enumerate(self._recent):
                        yield RadioButton(
                            _home_relative(path),
                            id=f"recent-{index}",
                            value=(index == 0),
                        )
                    yield RadioButton("Other path…", id="recent-other", value=False)
            yield Static(
                "Path to wordlist.txt:",
                id="open-path-label",
                classes="setup-prose",
            )
            initial = str(self._recent[0]) if self._recent else ""
            yield WordlistPathPicker(value=initial)
            yield _action_buttons(
                Button("Continue", id="btn-continue", variant="primary"),
                Button("Back", id="btn-back"),
            )
        yield Footer()

    def on_mount(self) -> None:
        self._sync_recent_path_ui()
        if self._recent:
            self.query_one("#recent-wordlist", RadioSet).focus()
        else:
            self._path_picker().focus_input()

    def _other_path_selected(self) -> bool:
        if not self._recent:
            return True
        pressed = self.query_one("#recent-wordlist", RadioSet).pressed_button
        return pressed is not None and pressed.id == "recent-other"

    def _sync_recent_path_ui(self) -> None:
        show_picker = self._other_path_selected()
        self.query_one("#open-path-label", Static).display = show_picker
        picker = self._path_picker()
        picker.display = show_picker
        if show_picker:
            picker.focus_input()

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        if event.radio_set.id != "recent-wordlist":
            return
        pressed = event.radio_set.pressed_button
        if pressed is not None and pressed.id and pressed.id.startswith("recent-"):
            if pressed.id != "recent-other":
                try:
                    index = int(pressed.id.rsplit("-", 1)[1])
                except ValueError:
                    index = -1
                if 0 <= index < len(self._recent):
                    self._path_picker().path_value = str(self._recent[index])
        self._sync_recent_path_ui()

    def _resolve_open_path(self) -> str | None:
        if not self._other_path_selected():
            pressed = self.query_one("#recent-wordlist", RadioSet).pressed_button
            if pressed is None or not pressed.id:
                self.notify("Choose a recent word list or Other path…", severity="error")
                return None
            try:
                index = int(pressed.id.rsplit("-", 1)[1])
            except ValueError:
                self.notify("Choose a recent word list or Other path…", severity="error")
                return None
            if 0 <= index < len(self._recent):
                return str(self._recent[index])
            self.notify("Choose a recent word list or Other path…", severity="error")
            return None
        return self.commit_path_picker_value()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
            return
        if event.button.id == "btn-continue":
            raw = self._resolve_open_path()
            if raw is None:
                return
            try:
                path, _detail = self._controller.validate_setup_wordlist(raw)
            except ValueError as exc:
                self.notify(str(exc), severity="error")
                return
            if not path.is_file():
                self.notify("That wordlist.txt does not exist yet.", severity="error")
                return
            self._controller.set_project_wordlist(path)
            self.app.pop_screen()
            self.app.pop_screen()
            from .dashboard import DashboardScreen

            self.app.push_screen(DashboardScreen(self._controller))

    def action_back(self) -> None:
        self.app.pop_screen()


class SetupWordlistScreen(_PathCompleteMixin, Screen[None]):
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("tab", "complete_path", "Complete", priority=True),
    ]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller
        self._presets = self._controller.setup_wordlist_presets()
        self._selected_preset_index = 0
        self._custom_visible = False

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="setup-body", classes="setup-body"):
            yield Static(id="wordlist-content", classes="setup-prose")
            with RadioSet(id="wordlist-preset"):
                for index, (label, _path) in enumerate(self._presets):
                    yield RadioButton(label, id=f"wordlist-preset-{index}", value=(index == 0))
                yield RadioButton("Custom path…", id="wordlist-preset-custom", value=False)
            yield Static(id="wordlist-path-hint", classes="setup-prose")
            yield WordlistPathPicker(value=str(self._controller.setup_wordlist_default()))
            yield _action_buttons(
                Button(WORDLIST_SETUP_RECOMMENDED_BUTTON, id="btn-recommended", variant="primary"),
                Button("Continue", id="btn-continue"),
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
            WHY_THIS_IS_SAFE_SHORT,
            "",
            WORDLIST_SETUP_STORAGE_REMINDER,
        ]
        if hint and hint != WORDLIST_SETUP_STORAGE_REMINDER:
            lines.extend(["", hint])
        self.query_one("#wordlist-content", Static).update("\n".join(lines))
        self._set_custom_visible(False)

    def _set_custom_visible(self, visible: bool) -> None:
        self._custom_visible = visible
        hint = self.query_one("#wordlist-path-hint", Static)
        picker = self._path_picker()
        recommended = self.query_one("#btn-recommended", Button)
        continue_btn = self.query_one("#btn-continue", Button)
        if visible:
            hint.update(_PATH_HINT)
            hint.display = True
            picker.display = True
            # Primary "Use selected folder" always advances a preset index and
            # ignores the path field — hide it in Custom so Enter/click cannot
            # silently keep Documents.
            recommended.display = False
            continue_btn.variant = "primary"
        else:
            hint.update("")
            hint.display = False
            picker.display = False
            recommended.display = True
            recommended.variant = "primary"
            continue_btn.variant = "default"

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        pressed_id = event.pressed.id or ""
        if pressed_id == "wordlist-preset-custom":
            self._set_custom_visible(True)
            # Do not leave the Documents preset sitting in the box — Continue
            # would silently reuse it if the user only browses the list.
            self._path_picker().path_value = "~/"
            self._path_picker().focus_input()
            return
        if pressed_id.startswith("wordlist-preset-"):
            index = int(pressed_id.rsplit("-", 1)[-1])
            self._selected_preset_index = index
            self._path_picker().path_value = str(self._presets[index][1])
            self._set_custom_visible(False)

    def _advance_with_path(self, raw: str) -> None:
        try:
            path, detail = self._controller.validate_setup_wordlist(raw)
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return
        self._controller.set_setup_wordlist(path)
        from .setup_targets_screen import SetupTargetsScreen

        self.app.push_screen(SetupTargetsScreen(self._controller, detail or ""))

    def _preset_paths(self) -> set[str]:
        return {str(path) for _label, path in self._presets}

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
            return
        if event.button.id == "btn-recommended":
            if self._custom_visible:
                # Defensive: button should be hidden; never apply Documents.
                raw = self.commit_path_picker_value(stale_defaults=self._preset_paths())
                if raw is None:
                    return
                self._advance_with_path(raw)
                return
            if not self._presets:
                self.notify("No recommended folder is available.", severity="error")
                return
            index = min(self._selected_preset_index, len(self._presets) - 1)
            self._advance_with_path(str(self._presets[index][1]))
            return
        if event.button.id == "btn-continue":
            if self._custom_visible:
                raw = self.commit_path_picker_value(stale_defaults=self._preset_paths())
                if raw is None:
                    return
                self._advance_with_path(raw)
                return
            # Preset mode: use the selected radio, not a stale hidden picker value.
            index = min(self._selected_preset_index, len(self._presets) - 1)
            self._advance_with_path(str(self._presets[index][1]))

    def action_back(self) -> None:
        self.app.pop_screen()


class ChangeWordlistScreen(_PathCompleteMixin, Screen[None]):
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("tab", "complete_path", "Complete", priority=True),
    ]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller
        self._recent = controller.recent_wordlists()
        self._selected_recent_index: int | None = 0 if self._recent else None
        current = controller.project_wordlist
        if current is not None and self._recent:
            try:
                current_resolved = current.expanduser().resolve()
            except OSError:
                current_resolved = None
            matched = False
            if current_resolved is not None:
                for index, path in enumerate(self._recent):
                    if path == current_resolved:
                        self._selected_recent_index = index
                        matched = True
                        break
            if not matched:
                self._selected_recent_index = None  # Other path…

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="setup-body", classes="setup-body"):
            body = f"{CHANGE_WORDLIST_HEADING}\n\n{CHANGE_WORDLIST_BODY}"
            if self._recent:
                body += "\n\nPick a recent word list, or choose Other path…"
            else:
                body += f"\n\n{_PATH_HINT}"
            yield Static(body, id="change-wordlist-content", classes="setup-prose")
            if self._recent:
                yield Static("Recent word lists:", classes="setup-prose")
                with RadioSet(id="recent-wordlist"):
                    for index, path in enumerate(self._recent):
                        yield RadioButton(
                            _home_relative(path),
                            id=f"recent-{index}",
                            value=(self._selected_recent_index == index),
                        )
                    yield RadioButton(
                        "Other path…",
                        id="recent-other",
                        value=(self._selected_recent_index is None),
                    )
            yield Static(
                "Path to wordlist.txt:",
                id="change-path-label",
                classes="setup-prose",
            )
            current = self._controller.project_wordlist
            initial = (
                str(current)
                if current is not None
                else (str(self._recent[0]) if self._recent else "")
            )
            yield WordlistPathPicker(value=initial)
            yield _action_buttons(
                Button("Continue", id="btn-continue", variant="primary"),
                Button("Back", id="btn-back"),
            )
        yield Footer()

    def on_mount(self) -> None:
        self._sync_recent_path_ui()
        if self._recent and not self._other_path_selected():
            self.query_one("#recent-wordlist", RadioSet).focus()
        else:
            self._path_picker().focus_input()

    def _other_path_selected(self) -> bool:
        if not self._recent:
            return True
        pressed = self.query_one("#recent-wordlist", RadioSet).pressed_button
        return pressed is not None and pressed.id == "recent-other"

    def _sync_recent_path_ui(self) -> None:
        show_picker = self._other_path_selected()
        self.query_one("#change-path-label", Static).display = show_picker
        picker = self._path_picker()
        picker.display = show_picker
        if show_picker:
            picker.focus_input()

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        if event.radio_set.id != "recent-wordlist":
            return
        pressed = event.radio_set.pressed_button
        if pressed is not None and pressed.id and pressed.id.startswith("recent-"):
            if pressed.id != "recent-other":
                try:
                    index = int(pressed.id.rsplit("-", 1)[1])
                except ValueError:
                    index = -1
                if 0 <= index < len(self._recent):
                    self._path_picker().path_value = str(self._recent[index])
        self._sync_recent_path_ui()

    def _resolve_change_path(self) -> str | None:
        if not self._other_path_selected():
            pressed = self.query_one("#recent-wordlist", RadioSet).pressed_button
            if pressed is None or not pressed.id:
                self.notify("Choose a recent word list or Other path…", severity="error")
                return None
            try:
                index = int(pressed.id.rsplit("-", 1)[1])
            except ValueError:
                self.notify("Choose a recent word list or Other path…", severity="error")
                return None
            if 0 <= index < len(self._recent):
                return str(self._recent[index])
            self.notify("Choose a recent word list or Other path…", severity="error")
            return None
        # Do not treat the prefilled current wordlist as "stale": Continue with
        # no edits must keep it. List commit runs only for directory prefixes.
        return self.commit_path_picker_value()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()
            return
        if event.button.id == "btn-continue":
            raw = self._resolve_change_path()
            if raw is None:
                return
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
        self._existing_config_conflict = False

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="setup-body", classes="setup-body"):
            yield Static(id="preview-content", classes="setup-prose")
            yield _action_buttons(
                Button("Create project", id="btn-create", variant="primary"),
                Button("Open this project", id="btn-open-existing", variant="primary"),
                Button("Back", id="btn-back"),
            )
        yield Footer()

    def on_mount(self) -> None:
        from ...project_setup.discovery import target_display_name

        self._prepared = self._controller.prepare_setup_preview()
        prepared = self._prepared
        discovery = self._controller.setup_target_discovery()
        selected = set(prepared.selected_target_ids)
        self._existing_config_conflict = any(
            "spell-sync.toml already exists" in item for item in prepared.conflicts
        )
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
            elif item.action.value == "conflict":
                lines.append(f"  {item.relative_name} (already exists — blocks create)")
        strategy = self._controller.setup_storage_strategy()
        if strategy is not None:
            lines.extend(
                [
                    "",
                    "Keeping this list:",
                    f"  {STORAGE_PREVIEW_LABELS.get(strategy, strategy)}",
                ]
            )
        lines.extend(["", "Enabled apps:"])
        enabled_names = [target_display_name(target_id) for target_id in prepared.enabled_targets]
        if enabled_names:
            lines.extend(f"  {name}" for name in enabled_names)
        else:
            lines.append("  (none)")
        declined = [
            target
            for target in discovery.targets
            if target.identifier not in selected and target.selectable
        ]
        unavailable = [
            target
            for target in discovery.targets
            if target.identifier not in selected and not target.selectable
        ]
        if declined:
            lines.extend(["", "Not enabled:"])
            lines.extend(f"  {target.display_name}" for target in declined)
        if unavailable:
            lines.extend(["", "Unavailable:"])
            for target in unavailable:
                detail = target.detail or target.status.replace("_", " ")
                lines.append(f"  {target.display_name} · {detail}")
        lines.extend(["", "External dictionaries:", "  No changes will be made."])
        if prepared.warnings:
            lines.extend(["", "Warnings:"])
            lines.extend(f"  · {warning}" for warning in prepared.warnings)
        if prepared.conflicts:
            lines.extend(["", "Cannot create project:"])
            lines.extend(f"  × {conflict}" for conflict in prepared.conflicts)
            if self._existing_config_conflict:
                lines.extend(
                    [
                        "",
                        "This folder already has a Spell Sync project.",
                        "Use Open this project, then Applications on the",
                        "dashboard if you need to change which apps are enabled.",
                    ]
                )
        self.query_one("#preview-content", Static).update("\n".join(lines))
        create_btn = self.query_one("#btn-create", Button)
        open_btn = self.query_one("#btn-open-existing", Button)
        if prepared.can_execute:
            create_btn.disabled = False
            create_btn.display = True
            open_btn.display = False
        elif self._existing_config_conflict:
            create_btn.display = False
            open_btn.display = True
            open_btn.disabled = False
        else:
            create_btn.disabled = True
            create_btn.display = True
            open_btn.display = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_back()
            return
        if event.button.id == "btn-open-existing" and self._prepared is not None:
            self._open_existing_project()
            return
        if (
            event.button.id == "btn-create"
            and self._prepared is not None
            and self._prepared.can_execute
        ):
            from .operation_screen import OperationScreen

            self.app.push_screen(
                OperationScreen(
                    self._controller,
                    operation="setup",
                    setup_prepared=self._prepared,
                )
            )

    def _open_existing_project(self) -> None:
        assert self._prepared is not None
        # Capture before popping — this screen may be dismissed first.
        app = self.app
        controller = self._controller
        wordlist = self._prepared.wordlist_path
        controller.set_project_wordlist(wordlist)
        from .dashboard import DashboardScreen

        # Wizard-first stacks are [base Screen, Setup*, …] with no Dashboard yet.
        # switch_screen() against Textual's empty base Screen raises IndexError
        # (empty _result_callbacks). Pop to the base, then push Dashboard.
        while len(app.screen_stack) > 1:
            current = app.screen
            if isinstance(current, DashboardScreen):
                current.refresh_dashboard()
                return
            app.pop_screen()
        if isinstance(app.screen, DashboardScreen):
            app.screen.refresh_dashboard()
            return
        app.push_screen(DashboardScreen(controller))

    def action_back(self) -> None:
        self.app.pop_screen()
