"""Hybrid family enable + per-dictionary exclusions."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from spell_sync.dictionaries import Dictionary, DictionaryFormat, discover_dictionaries
from spell_sync.project_setup import discovery as discovery_mod
from spell_sync.project_setup.discovery import discover_setup_targets
from spell_sync.project_setup.draft import ProjectConfigDraft, SafetyConfig
from spell_sync.project_setup.render import render_project_config
from spell_sync.project_setup.selection import (
    selection_from_enabled,
    toggle_dictionary_inclusion,
)
from spell_sync.read_outcome import ReadStatus
from spell_sync.runtime_settings import RuntimeSettings
from spell_sync.settings import ConfigStatus, load_config_result


def test_excluded_array_parses_into_runtime_settings(tmp_path: Path) -> None:
    config = tmp_path / "spell-sync.toml"
    config.write_text(
        '[dictionaries]\nchrome = true\nexcluded = ["editor:vscode", "macos-applespell"]\n',
        encoding="utf-8",
    )
    wordlist = tmp_path / "wordlist.txt"
    wordlist.write_text("alpha\n", encoding="utf-8")
    result = load_config_result(wordlist=wordlist)
    assert result.status is ConfigStatus.VALID
    settings = result.runtime_settings()
    assert settings.dictionaries.excluded == frozenset({"editor:vscode", "macos-applespell"})


def test_discover_dictionaries_applies_exclusions() -> None:
    settings = RuntimeSettings.from_config_dict(
        {"dictionaries": {"editors": True, "excluded": ["editor:vscode"]}}
    )
    with patch(
        "spell_sync.dictionaries.discover_from_sources",
        return_value=[
            Dictionary("editor:cursor", "/c", DictionaryFormat.TEXT),
            Dictionary("editor:vscode", "/v", DictionaryFormat.TEXT),
        ],
    ):
        found = discover_dictionaries(settings)
    assert [item.name for item in found] == ["editor:cursor"]


def test_setup_discovery_keeps_excluded_names_visible() -> None:
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
                        MagicMock(status=ReadStatus.OK, words=["a"], detail=None),
                        MagicMock(status=ReadStatus.OK, words=["b"], detail=None),
                    ],
                ):
                    rows = discover_setup_targets().targets
    editors = next(row for row in rows if row.identifier == "editors")
    assert editors.dictionary_word_counts == (("editor:cursor", 1), ("editor:vscode", 1))


def test_toggle_dictionary_inclusion_and_render() -> None:
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
                        MagicMock(status=ReadStatus.OK, words=["a"], detail=None),
                        MagicMock(status=ReadStatus.OK, words=["b"], detail=None),
                    ],
                ):
                    discovery = discover_setup_targets(enabled_targets=frozenset({"editors"}))
    selection = selection_from_enabled(discovery, frozenset({"editors"}))
    updated = toggle_dictionary_inclusion(selection, discovery, "editor:vscode")
    assert updated.excluded_dictionary_names == frozenset({"editor:vscode"})
    # Cannot exclude the last included dictionary.
    blocked = toggle_dictionary_inclusion(updated, discovery, "editor:cursor")
    assert blocked == updated
    rendered = render_project_config(
        ProjectConfigDraft(
            1,
            ("editors",),
            SafetyConfig(),
            excluded_dictionaries=("editor:vscode",),
        )
    ).decode("utf-8")
    assert 'excluded = ["editor:vscode"]' in rendered
