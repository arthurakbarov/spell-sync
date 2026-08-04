"""Golden byte snapshots for dictionary writers (Chrome / text / Hunspell / JetBrains / JSON)."""

from __future__ import annotations

from pathlib import Path

import pytest

from spell_sync.io import (
    write_chrome_words,
    write_hunspell_words,
    write_jetbrains_words,
    write_json_words,
    write_text_words,
)

ROOT = Path(__file__).resolve().parents[1]
GOLDENS = ROOT / "tests" / "goldens" / "writers"

# Fixed multi-script sample; sort_words uses casefold → alpha, Beta, слово.
_WORDS = ("Beta", "alpha", "слово")


def _assert_matches_golden(path: Path, relative: str) -> None:
    expected = GOLDENS / relative
    assert expected.is_file(), f"missing golden {expected}"
    assert path.read_bytes() == expected.read_bytes(), (
        f"writer output drifted from {relative}; update golden only with intentional format change"
    )


@pytest.mark.core
def test_chrome_writer_golden(tmp_path: Path) -> None:
    path = tmp_path / "Custom Dictionary.txt"
    assert write_chrome_words(path, _WORDS, quiet=True)
    _assert_matches_golden(path, "chrome_custom_dictionary.txt")


@pytest.mark.core
def test_firefox_text_writer_golden(tmp_path: Path) -> None:
    path = tmp_path / "persdict.dat"
    assert write_text_words(path, _WORDS, "utf-8", False, quiet=True)
    _assert_matches_golden(path, "firefox_persdict.dat")


@pytest.mark.core
def test_hunspell_writer_golden(tmp_path: Path) -> None:
    path = tmp_path / "custom.dic"
    assert write_hunspell_words(path, _WORDS, quiet=True)
    _assert_matches_golden(path, "hunspell_custom.dic")


@pytest.mark.core
def test_jetbrains_writer_golden(tmp_path: Path) -> None:
    path = tmp_path / "cachedDictionary.xml"
    assert write_jetbrains_words(path, _WORDS, quiet=True)
    _assert_matches_golden(path, "jetbrains_cachedDictionary.xml")


@pytest.mark.core
def test_json_sublime_writer_golden(tmp_path: Path) -> None:
    path = tmp_path / "Preferences.sublime-settings"
    assert write_json_words(path, _WORDS, quiet=True)
    _assert_matches_golden(path, "sublime_preferences.json")
