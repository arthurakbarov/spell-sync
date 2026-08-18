"""Core tests for setup target selection."""

import tomllib
from pathlib import Path

from spell_sync.application import SpellSyncService
from spell_sync.project_setup.discovery import (
    SetupTarget,
    SetupTargetDiscovery,
    discover_setup_targets,
)
from spell_sync.project_setup.draft import SetupDraft
from spell_sync.project_setup.execute import execute_project_setup
from spell_sync.project_setup.prepare import prepare_project_setup
from spell_sync.project_setup.render import render_project_config
from spell_sync.project_setup.selection import (
    SetupSelection,
    clear_selectable_targets,
    default_selection,
    merge_selection_after_refresh,
    select_available_targets,
    toggle_target,
)
from spell_sync.settings import load_config_result


def _target(
    identifier: str,
    *,
    selectable: bool = True,
    enabled_by_default: bool = True,
    status: str = "ok",
    detail: str | None = None,
) -> SetupTarget:
    return SetupTarget(
        identifier=identifier,
        display_name=identifier.title(),
        path=Path(f"/tmp/{identifier}.txt"),
        format_name="text",
        detected=True,
        available=True,
        readable=True,
        supported=True,
        enabled_by_default=enabled_by_default,
        selectable=selectable,
        word_count=3,
        status=status,
        detail=detail,
    )


def _discovery(*targets: SetupTarget) -> SetupTargetDiscovery:
    default_enabled = tuple(
        target.identifier for target in targets if target.enabled_by_default and target.selectable
    )
    return SetupTargetDiscovery(targets=targets, default_enabled=default_enabled)


def test_default_selection_uses_selectable_defaults() -> None:
    discovery = _discovery(
        _target("chrome"),
        _target("jetbrains", selectable=False, enabled_by_default=False, status="missing"),
    )
    selection = default_selection(discovery)
    assert selection.selected_target_ids == frozenset({"chrome"})


def test_toggle_selectable_target() -> None:
    discovery = _discovery(_target("chrome"), _target("firefox"))
    selection = SetupSelection(frozenset({"chrome"}))
    updated = toggle_target(selection, discovery, "firefox")
    assert updated.selected_target_ids == frozenset({"chrome", "firefox"})


def test_toggle_corrupt_target_is_ignored() -> None:
    discovery = _discovery(
        _target("chrome"),
        _target(
            "not-a-config-target",
            selectable=False,
            enabled_by_default=False,
            status="corrupt",
        ),
    )
    selection = SetupSelection(frozenset({"chrome"}))
    updated = toggle_target(selection, discovery, "not-a-config-target")
    assert updated == selection


def test_select_available_and_clear() -> None:
    discovery = _discovery(_target("chrome"), _target("firefox"))
    selection = SetupSelection(frozenset())
    selected = select_available_targets(selection, discovery)
    assert selected.selected_target_ids == frozenset({"chrome", "firefox"})
    cleared = clear_selectable_targets(selected, discovery)
    assert cleared.selected_target_ids == frozenset()


def test_refresh_keeps_valid_selection_and_adds_new_defaults() -> None:
    previous = SetupSelection(frozenset({"chrome"}))
    old_discovery = _discovery(
        _target("chrome"), _target("jetbrains", selectable=False, enabled_by_default=False)
    )
    new_discovery = _discovery(
        _target("chrome"),
        _target("firefox"),
        _target(
            "not-a-config-target",
            selectable=False,
            enabled_by_default=False,
            status="corrupt",
        ),
    )
    merged = merge_selection_after_refresh(
        previous,
        frozenset(target.identifier for target in old_discovery.targets),
        new_discovery,
    )
    assert merged.selected_target_ids == frozenset({"chrome", "firefox"})


def test_refresh_preserves_non_selectable_but_selected() -> None:
    previous = SetupSelection(frozenset({"chrome", "obsidian"}))
    old_discovery = _discovery(_target("chrome"), _target("obsidian"))
    new_discovery = _discovery(
        _target("chrome"),
        _target(
            "obsidian",
            selectable=False,
            enabled_by_default=False,
            status="unreadable",
            detail="Unreadable dictionary",
        ),
    )
    merged = merge_selection_after_refresh(
        previous,
        frozenset(target.identifier for target in old_discovery.targets),
        new_discovery,
    )
    assert merged.selected_target_ids == frozenset({"chrome", "obsidian"})


def test_prepared_setup_carries_exact_selected_target_ids(tmp_path: Path) -> None:
    wordlist = tmp_path / "wordlist.txt"
    prepared = prepare_project_setup(
        SetupDraft(wordlist, ("chrome", "firefox"), create_wordlist=True)
    )
    assert prepared.selected_target_ids == ("chrome", "firefox")
    assert prepared.enabled_targets == ("chrome", "firefox")


def test_generated_toml_matches_selection(tmp_path: Path) -> None:
    wordlist = tmp_path / "wordlist.txt"
    draft = SetupDraft(wordlist, ("chrome", "firefox"), create_wordlist=True)
    prepared = prepare_project_setup(draft)
    execution = execute_project_setup(prepared, confirmed_setup_id=prepared.setup_id)
    assert execution.outcome.value == "completed"
    config_path = wordlist.parent / "spell-sync.toml"
    parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
    dictionaries = parsed["dictionaries"]
    assert dictionaries["chrome"] is True
    assert dictionaries["firefox"] is True
    assert dictionaries["jetbrains"] is False


def test_config_round_trip_preserves_selection(tmp_path: Path) -> None:
    draft = SetupDraft(
        tmp_path / "wordlist.txt",
        ("chrome", "firefox"),
        create_wordlist=True,
    )
    config = render_project_config(prepare_project_setup(draft).config_draft)
    config_path = tmp_path / "spell-sync.toml"
    config_path.write_bytes(config)
    (tmp_path / "wordlist.txt").write_text("alpha\n", encoding="utf-8")
    result = load_config_result(wordlist=tmp_path / "wordlist.txt")
    assert result.config is not None
    assert result.config["dictionaries"]["chrome"] is True
    assert result.config["dictionaries"]["firefox"] is True
    assert result.config["dictionaries"]["jetbrains"] is False


def test_setup_id_changes_when_selection_changes(tmp_path: Path) -> None:
    wordlist = tmp_path / "wordlist.txt"
    first = prepare_project_setup(SetupDraft(wordlist, ("chrome",), create_wordlist=True))
    second = prepare_project_setup(
        SetupDraft(wordlist, ("chrome", "firefox"), create_wordlist=True)
    )
    assert first.setup_id != second.setup_id


def test_deterministic_config_bytes() -> None:
    from spell_sync.project_setup.draft import ProjectConfigDraft, SafetyConfig

    draft = ProjectConfigDraft(1, ("chrome", "firefox"), SafetyConfig())
    first = render_project_config(draft)
    second = render_project_config(draft)
    assert first == second
    assert b"chrome = true" in first
    assert b"jetbrains = false" in first


def test_cli_init_uses_documented_defaults(tmp_path: Path, monkeypatch) -> None:
    from unittest.mock import patch

    from spell_sync.cli_options import CliOptions
    from spell_sync.commands import cmd_init

    monkeypatch.chdir(tmp_path)
    discovery = discover_setup_targets()
    with patch.object(SpellSyncService, "prepare_project_setup") as prepare:
        with patch.object(SpellSyncService, "execute_project_setup") as execute:
            with patch.object(SpellSyncService, "build_setup_report") as build_report:
                cmd_init(CliOptions())
    draft = prepare.call_args.args[0]
    assert draft.selected_targets == discovery.default_enabled
    execute.assert_called_once()
    build_report.assert_called_once()


def test_setup_does_not_modify_external_dictionaries(tmp_path: Path, monkeypatch) -> None:
    dictionary = tmp_path / "dictionaries" / "chrome.txt"
    dictionary.parent.mkdir(parents=True)
    original = b"alpha\nbeta\n"
    dictionary.write_bytes(original)

    def fake_discover(_config):
        from spell_sync.dictionaries import Dictionary, DictionaryFormat

        return [
            Dictionary(
                name="chrome:Default",
                path=str(dictionary),
                format=DictionaryFormat.CHROME,
            )
        ]

    monkeypatch.setattr(
        "spell_sync.project_setup.discovery.discover_dictionaries",
        fake_discover,
    )
    wordlist = tmp_path / "project" / "wordlist.txt"
    prepared = prepare_project_setup(SetupDraft(wordlist, ("chrome",), create_wordlist=True))
    execution = execute_project_setup(prepared, confirmed_setup_id=prepared.setup_id)
    assert execution.outcome.value == "completed"
    assert dictionary.read_bytes() == original


def test_target_by_id_helper() -> None:
    from spell_sync.project_setup.selection import _target_by_id

    discovery = _discovery(_target("chrome"))
    assert _target_by_id(discovery, "chrome") is not None
    assert _target_by_id(discovery, "missing") is None


def test_ambiguous_discovery_marks_target_unselectable() -> None:
    from unittest.mock import MagicMock, patch

    from spell_sync.project_setup import discovery as discovery_mod
    from spell_sync.read_outcome import ReadStatus

    dictionaries = [
        MagicMock(path="/a", format=MagicMock(value="text")),
        MagicMock(path="/b", format=MagicMock(value="text")),
    ]
    dictionaries[0].name = "chrome:A"
    dictionaries[1].name = "chrome:B"
    with patch.object(discovery_mod, "discover_dictionaries", return_value=dictionaries):
        with patch.object(
            discovery_mod,
            "dictionary_read_result",
            side_effect=[
                MagicMock(status=ReadStatus.OK, words=["a"], detail=None),
                MagicMock(status=ReadStatus.CORRUPT, words=None, detail="bad"),
            ],
        ):
            rows = discovery_mod.discover_setup_targets().targets
    chrome = next(row for row in rows if row.identifier == "chrome")
    assert chrome.selectable is False


def test_ambiguous_corrupt_and_unreadable() -> None:
    from unittest.mock import MagicMock, patch

    from spell_sync.project_setup import discovery as discovery_mod
    from spell_sync.read_outcome import ReadStatus

    dictionaries = [
        MagicMock(path="/a", format=MagicMock(value="text")),
        MagicMock(path="/b", format=MagicMock(value="text")),
    ]
    dictionaries[0].name = "chrome:A"
    dictionaries[1].name = "chrome:B"
    with patch.object(discovery_mod, "discover_dictionaries", return_value=dictionaries):
        with patch.object(
            discovery_mod,
            "dictionary_read_result",
            side_effect=[
                MagicMock(status=ReadStatus.CORRUPT, words=None, detail=None),
                MagicMock(status=ReadStatus.UNREADABLE, words=None, detail="locked"),
            ],
        ):
            rows = discovery_mod.discover_setup_targets().targets
    chrome = next(row for row in rows if row.identifier == "chrome")
    assert chrome.selectable is False


def test_corrupt_target_default_detail() -> None:
    from unittest.mock import MagicMock, patch

    from spell_sync.project_setup import discovery as discovery_mod
    from spell_sync.read_outcome import ReadStatus

    dictionary = MagicMock(path="/a", format=MagicMock(value="text"))
    dictionary.name = "chrome:Default"
    with patch.object(discovery_mod, "discover_dictionaries", return_value=[dictionary]):
        with patch.object(
            discovery_mod,
            "dictionary_read_result",
            return_value=MagicMock(status=ReadStatus.CORRUPT, words=None, detail=None),
        ):
            rows = discovery_mod.discover_setup_targets().targets
    chrome = next(row for row in rows if row.identifier == "chrome")
    assert chrome.detail == "Corrupt dictionary · cannot be enabled safely"


def test_win_spelling_platform_support(monkeypatch) -> None:
    from unittest.mock import MagicMock, patch

    from spell_sync.project_setup import discovery as discovery_mod
    from spell_sync.read_outcome import ReadStatus

    monkeypatch.setattr(discovery_mod, "is_macos", lambda: False)
    monkeypatch.setattr(discovery_mod, "is_windows", lambda: True)
    dictionary = MagicMock(path="/win/dict", format=MagicMock(value="text"))
    dictionary.name = "win-spelling"
    with patch.object(discovery_mod, "discover_dictionaries", return_value=[dictionary]):
        with patch.object(
            discovery_mod,
            "dictionary_read_result",
            return_value=MagicMock(status=ReadStatus.OK, words=["a"], detail=None),
        ):
            rows = discovery_mod.discover_setup_targets().targets
    win = next(row for row in rows if row.identifier == "win_spelling")
    assert win.supported is True


def test_multiple_ok_dictionaries_not_ambiguous() -> None:
    from unittest.mock import MagicMock, patch

    from spell_sync.project_setup import discovery as discovery_mod
    from spell_sync.read_outcome import ReadStatus

    dictionaries = [
        MagicMock(path="/a", format=MagicMock(value="text")),
        MagicMock(path="/b", format=MagicMock(value="text")),
    ]
    dictionaries[0].name = "chrome:A"
    dictionaries[1].name = "chrome:B"
    with patch.object(discovery_mod, "discover_dictionaries", return_value=dictionaries):
        with patch.object(
            discovery_mod,
            "dictionary_read_result",
            return_value=MagicMock(status=ReadStatus.OK, words=["a"], detail=None),
        ):
            rows = discovery_mod.discover_setup_targets().targets
    chrome = next(row for row in rows if row.identifier == "chrome")
    assert chrome.selectable is True


def test_classic_macos_name_maps_to_spelling_family() -> None:
    from spell_sync.project_setup.discovery import dictionary_family_id

    assert dictionary_family_id("macos") == "macos_spelling"
    assert dictionary_family_id("macos-applespell") == "macos_spelling"


def test_macos_ok_plus_unreadable_sibling_is_selectable() -> None:
    from unittest.mock import MagicMock, patch

    from spell_sync.project_setup import discovery as discovery_mod
    from spell_sync.read_outcome import ReadStatus

    dictionaries = [
        MagicMock(path="/classic", format=MagicMock(value="text")),
        MagicMock(path="/applespell", format=MagicMock(value="text")),
    ]
    dictionaries[0].name = "macos"
    dictionaries[1].name = "macos-applespell"
    with patch.object(discovery_mod, "is_macos", return_value=True):
        with patch.object(discovery_mod, "is_windows", return_value=False):
            with patch.object(discovery_mod, "discover_dictionaries", return_value=dictionaries):
                with patch.object(
                    discovery_mod,
                    "dictionary_read_result",
                    side_effect=[
                        MagicMock(status=ReadStatus.OK, words=["a", "b"], detail=None),
                        MagicMock(status=ReadStatus.UNREADABLE, words=None, detail="unreadable"),
                    ],
                ):
                    rows = discovery_mod.discover_setup_targets().targets
    macos = next(row for row in rows if row.identifier == "macos_spelling")
    assert macos.selectable is True
    assert macos.status == ReadStatus.OK.value
    assert macos.word_count == 2
    assert macos.dictionary_word_counts == (("macos", 2),)
    assert any(row.identifier == "macos" for row in rows) is False


def test_multi_dictionary_family_does_not_sum_word_counts() -> None:
    from unittest.mock import MagicMock, patch

    from spell_sync.project_setup import discovery as discovery_mod
    from spell_sync.project_setup.discovery import format_setup_target_word_meta
    from spell_sync.read_outcome import ReadStatus

    dictionaries = [
        MagicMock(path="/cursor", format=MagicMock(value="text")),
        MagicMock(path="/vscode", format=MagicMock(value="text")),
    ]
    dictionaries[0].name = "editor:cursor"
    dictionaries[1].name = "editor:vscode"
    with patch.object(discovery_mod, "is_macos", return_value=False):
        with patch.object(discovery_mod, "is_windows", return_value=False):
            with patch.object(discovery_mod, "discover_dictionaries", return_value=dictionaries):
                with patch.object(
                    discovery_mod,
                    "dictionary_read_result",
                    side_effect=[
                        MagicMock(status=ReadStatus.OK, words=["a"] * 10, detail=None),
                        MagicMock(status=ReadStatus.OK, words=["b"] * 10, detail=None),
                    ],
                ):
                    rows = discovery_mod.discover_setup_targets().targets
    editors = next(row for row in rows if row.identifier == "editors")
    assert editors.word_count is None
    assert editors.dictionary_word_counts == (
        ("editor:cursor", 10),
        ("editor:vscode", 10),
    )
    assert format_setup_target_word_meta(editors) == "2 dictionaries"
    assert "20" not in (format_setup_target_word_meta(editors) or "")


def test_discovery_ignores_selected_targets_gating() -> None:
    from unittest.mock import MagicMock, patch

    from spell_sync.project_setup import discovery as discovery_mod
    from spell_sync.read_outcome import ReadStatus

    dictionary = MagicMock(path="/a", format=MagicMock(value="text"))
    dictionary.name = "chrome:Default"
    with patch.object(
        discovery_mod, "discover_dictionaries", return_value=[dictionary]
    ) as discover:
        with patch.object(
            discovery_mod,
            "dictionary_read_result",
            return_value=MagicMock(status=ReadStatus.OK, words=["a"], detail=None),
        ):
            rows = discovery_mod.discover_setup_targets(
                enabled_targets=frozenset({"editors"}),
            ).targets
    chrome = next(row for row in rows if row.identifier == "chrome")
    assert chrome.selectable is True
    assert chrome.enabled is False
    # Discovery must probe with all families enabled, not only selected_targets.
    settings = discover.call_args.args[0]
    assert settings.dictionaries.chrome is True
    assert settings.dictionaries.macos_spelling is True


def test_win_spelling_empty_group_on_windows(monkeypatch) -> None:
    from unittest.mock import patch

    from spell_sync.project_setup import discovery as discovery_mod

    monkeypatch.setattr(discovery_mod, "is_macos", lambda: False)
    monkeypatch.setattr(discovery_mod, "is_windows", lambda: True)
    with patch.object(discovery_mod, "discover_dictionaries", return_value=[]):
        rows = discovery_mod.discover_setup_targets().targets
    win = next(row for row in rows if row.identifier == "win_spelling")
    assert win.detected is False
    assert win.selectable is False
    assert win.supported is True


def test_controller_selection_helpers() -> None:
    from unittest.mock import MagicMock

    from spell_sync.application.requests import ProjectRef
    from spell_sync.tui.controller import TuiController
    from tests.tui.fake_service import fake_service

    discovery = _discovery(_target("chrome"), _target("firefox"))
    service = fake_service()
    service.discover_setup_targets = MagicMock(return_value=discovery)
    controller = TuiController(service, ProjectRef())
    controller.set_setup_wordlist(Path("/tmp/setup/wordlist.txt"))
    assert controller.setup_selection().selected_target_ids
    controller.clear_setup_target_selection()
    controller.select_available_setup_targets()
    assert "chrome" in controller.setup_selected_targets
    controller.toggle_setup_target("firefox")
    controller.refresh_setup_target_discovery()
    controller.refresh_setup_targets()
    assert controller.setup_target_discovery().targets


def test_stale_prepared_setup_rejected_after_selection_change(tmp_path: Path) -> None:
    wordlist = tmp_path / "wordlist.txt"
    prepared = prepare_project_setup(SetupDraft(wordlist, ("chrome",), create_wordlist=True))
    execution = execute_project_setup(prepared, confirmed_setup_id="wrong-id")
    assert execution.outcome.value == "failed"


def test_render_push_bool_default_without_existing_config() -> None:
    from spell_sync.project_setup.render import _push_bool

    assert _push_bool(None, "strict", False) is False


def test_dictionary_family_aliases_map_to_config_ids() -> None:
    from spell_sync.project_setup.discovery import dictionary_family_id

    assert dictionary_family_id("editor") == "editors"
    assert dictionary_family_id("nvim") == "neovim"
    assert dictionary_family_id("nvim-en") == "neovim"
    assert dictionary_family_id("sublime") == "sublime"


def test_sublime_is_selectable_when_readable(tmp_path: Path) -> None:
    from unittest.mock import MagicMock, patch

    from spell_sync.project_setup import discovery as discovery_mod
    from spell_sync.read_outcome import ReadStatus

    dictionary = MagicMock()
    dictionary.name = "sublime"
    dictionary.path = str(tmp_path / "Preferences.sublime-settings")
    dictionary.format = MagicMock(value="json")
    with patch.object(discovery_mod, "discover_dictionaries", return_value=[dictionary]):
        with patch.object(
            discovery_mod,
            "dictionary_read_result",
            return_value=MagicMock(status=ReadStatus.OK, words=["alpha"], detail=None),
        ):
            rows = discovery_mod.discover_setup_targets().targets
    sublime = next(row for row in rows if row.identifier == "sublime")
    assert sublime.selectable is True
    assert sublime.enabled_by_default is True
