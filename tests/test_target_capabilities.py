"""Tests for spell_sync.target_capabilities."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from spell_sync.dictionaries import discover_dictionaries
from spell_sync.project_setup.discovery import _CONFIG_TARGET_IDS
from spell_sync.runtime_settings import RuntimeSettings
from spell_sync.target_capabilities import (
    DICTIONARY_FILTER_KINDS,
    TARGET_CAPABILITIES,
    TargetFilterKind,
    all_capability_identifiers,
    capability_by_id,
    config_target_identifiers,
    platform_capability_identifiers,
)
from spell_sync.words import subset_english, subset_russian


def test_unique_identifiers() -> None:
    ids = [item.identifier for item in TARGET_CAPABILITIES]
    assert len(ids) == len(set(ids))


def test_deterministic_ordering() -> None:
    ids = [item.identifier for item in TARGET_CAPABILITIES]
    assert ids == sorted(ids)


def test_covers_config_target_identifiers() -> None:
    assert config_target_identifiers() <= all_capability_identifiers()


def test_includes_platform_targets() -> None:
    assert platform_capability_identifiers() <= all_capability_identifiers()


def test_no_unknown_registry_entries_vs_config() -> None:
    extra = (
        all_capability_identifiers()
        - config_target_identifiers()
        - platform_capability_identifiers()
    )
    assert extra == frozenset()


@pytest.mark.parametrize(
    ("dictionary_name", "expected"),
    [
        ("win-en", TargetFilterKind.LATIN),
        ("win-en-gb", TargetFilterKind.LATIN),
        ("win-ru", TargetFilterKind.CYRILLIC_AND_NON_LATIN),
    ],
)
def test_dictionary_subset_metadata(dictionary_name: str, expected: TargetFilterKind) -> None:
    assert DICTIONARY_FILTER_KINDS[dictionary_name] is expected


def test_dictionary_subset_functions_match_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("spell_sync.dictionaries.is_windows", lambda: True)
    monkeypatch.setattr("spell_sync.dictionaries.is_macos", lambda: False)
    config = {"dictionaries": {name: True for name in _CONFIG_TARGET_IDS}, "push": {}, "io": {}}
    dictionaries = discover_dictionaries(RuntimeSettings.from_config_dict(config))
    by_name = {item.name: item for item in dictionaries}
    assert by_name["win-en"].subset is subset_english
    assert by_name["win-en-gb"].subset is subset_english
    assert by_name["win-ru"].subset is subset_russian
    for name, dictionary in by_name.items():
        if name.startswith("macos-") or name.startswith("chrome:"):
            assert dictionary.subset is None


def test_ordinary_targets_full_filter() -> None:
    for identifier in ("chrome", "firefox", "editors", "jetbrains"):
        capability = capability_by_id(identifier)
        assert capability is not None
        assert capability.filter_kind is TargetFilterKind.FULL


def test_win_spelling_locale_specific() -> None:
    capability = capability_by_id("win_spelling")
    assert capability is not None
    assert capability.filter_kind is TargetFilterKind.LOCALE_SPECIFIC


def test_registry_has_no_paths() -> None:
    root = Path(__file__).resolve().parents[1] / "spell_sync" / "target_capabilities.py"
    tree = ast.parse(root.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            if value.startswith("/") or value.startswith("~"):
                pytest.fail(f"registry must not contain path literal: {value!r}")


def test_registry_does_not_import_textual() -> None:
    source = Path(__file__).resolve().parents[1] / "spell_sync" / "target_capabilities.py"
    assert "textual" not in source.read_text(encoding="utf-8").lower()


def test_all_descriptors_frozen() -> None:
    for capability in TARGET_CAPABILITIES:
        with pytest.raises(Exception):
            capability.display_name = "changed"  # type: ignore[misc]


def test_capability_by_id_missing() -> None:
    assert capability_by_id("missing-target") is None


def test_registry_module_has_no_filesystem_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_open(*args: object, **kwargs: object) -> object:
        raise AssertionError("registry must not open files at import time")

    monkeypatch.setattr("pathlib.Path.open", fail_open)
    importlib.reload(importlib.import_module("spell_sync.target_capabilities"))


def test_discovery_alias_mapping() -> None:
    from spell_sync.target_capabilities import (
        capability_for_discovery_target,
        resolve_capability_identifier,
    )

    assert resolve_capability_identifier("editor") == "editors"
    assert resolve_capability_identifier("nvim-en") == "neovim"
    capability = capability_for_discovery_target("editor")
    assert capability is not None
    assert capability.identifier == "editors"


def test_validation_matrix_covers_registry() -> None:
    import json

    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "docs" / "target-validation.json").read_text(encoding="utf-8"))
    pairs = {
        (row["target_id"], row["platform"]) for row in data["targets"] if isinstance(row, dict)
    }
    from spell_sync.target_capabilities import registry_target_platform_pairs

    assert pairs == set(registry_target_platform_pairs())


def test_supported_targets_matrix_not_stale() -> None:
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "check_target_capabilities.py"), "--check"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
