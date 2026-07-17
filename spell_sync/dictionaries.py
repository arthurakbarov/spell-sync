"""Local dictionary description and discovery."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional

from .config import (
    SUBLIME_PACKAGE,
    enable_brave,
    enable_chrome,
    enable_edge,
    enable_editors,
    enable_firefox,
    enable_hunspell,
    enable_jetbrains,
    enable_libreoffice,
    enable_neovim,
    enable_obsidian,
    enable_vivaldi,
)
from .dictionary_registry import DictionarySource, discover_from_sources
from .io import (
    read_chrome_words,
    read_hunspell_words,
    read_jetbrains_words,
    read_json_words,
    read_text_words,
    write_chrome_words,
    write_hunspell_words,
    write_jetbrains_words,
    write_json_words,
    write_text_words,
)
from .log import log
from .paths import (
    app_support_dir,
    brave_dict_paths,
    chrome_dict_paths,
    edge_dict_paths,
    editor_dict_paths,
    firefox_dict_paths,
    hunspell_dict_paths,
    is_macos,
    is_windows,
    jetbrains_dict_paths,
    libreoffice_dict_paths,
    macos_dictionary_paths,
    neovim_dict_paths,
    obsidian_dict_paths,
    sublime_packages_dir,
    vivaldi_dict_paths,
)
from .settings import bind_active_settings
from .words import WordSet, subset_english, subset_russian

SubsetFn = Callable[[WordSet], WordSet]


# --- Types ---


class DictionaryFormat(str, Enum):
    CHROME = "chrome"
    HUNSPELL = "hunspell"
    JSON = "json"
    JETBRAINS = "jetbrains"
    TEXT = "text"


@dataclass(frozen=True)
class Dictionary:
    """Local dictionary for one application."""

    name: str
    path: str
    format: DictionaryFormat
    encoding: str = "utf-8"
    bom: bool = False
    subset: Optional[SubsetFn] = None

    def target_words(self, wordlist: WordSet) -> WordSet:
        return self.subset(wordlist) if self.subset else wordlist

    def read(self, *, quiet: bool | None = None) -> WordSet:
        readers = {
            DictionaryFormat.JSON: read_json_words,
            DictionaryFormat.CHROME: read_chrome_words,
            DictionaryFormat.HUNSPELL: read_hunspell_words,
            DictionaryFormat.JETBRAINS: read_jetbrains_words,
        }
        reader = readers.get(self.format, read_text_words)
        return reader(self.path, quiet=quiet)

    def write(self, wordlist: WordSet, *, quiet: bool | None = None) -> bool:
        words = self.target_words(wordlist)
        writers = {
            DictionaryFormat.JSON: lambda: write_json_words(self.path, words, quiet=quiet),
            DictionaryFormat.CHROME: lambda: write_chrome_words(self.path, words, quiet=quiet),
            DictionaryFormat.HUNSPELL: lambda: write_hunspell_words(self.path, words, quiet=quiet),
            DictionaryFormat.JETBRAINS: lambda: write_jetbrains_words(
                self.path, words, quiet=quiet
            ),
        }
        write_fn = writers.get(self.format)
        if write_fn is not None:
            return write_fn()
        return write_text_words(self.path, words, self.encoding, self.bom, quiet=quiet)


# --- Discovery ---


def _dictionary_physical_key(path: str) -> str:
    """Deduplication key: one inode/file — one dictionary."""
    target = Path(path)
    try:
        stat = os.stat(target, follow_symlinks=True)
        return f"{stat.st_dev}:{stat.st_ino}"
    except OSError:
        pass
    try:
        if target.exists() or target.is_symlink():
            return str(target.resolve())
    except OSError:
        pass
    return path


def _dedupe_dictionaries(dictionaries: List[Dictionary]) -> List[Dictionary]:
    seen: dict[str, str] = {}
    unique: List[Dictionary] = []
    for dictionary in dictionaries:
        key = _dictionary_physical_key(dictionary.path)
        if key in seen:
            log.warn(f"  {dictionary.name}: same file as {seen[key]} — dictionary skipped")
            continue
        seen[key] = dictionary.name
        unique.append(dictionary)
    return unique


def _windows_spelling_path(locale: str) -> str:
    appdata = app_support_dir()
    return str(appdata / "Microsoft" / "Spelling" / locale / "default.dic")


def _platform_dictionaries() -> List[Dictionary]:
    dictionaries: List[Dictionary] = []
    if is_windows():
        dictionaries.extend(
            [
                Dictionary(
                    "win-ru",
                    _windows_spelling_path("ru-RU"),
                    DictionaryFormat.TEXT,
                    encoding="utf-16-le",
                    bom=True,
                    subset=subset_russian,
                ),
                Dictionary(
                    "win-en",
                    _windows_spelling_path("en-US"),
                    DictionaryFormat.TEXT,
                    encoding="utf-16-le",
                    bom=True,
                    subset=subset_english,
                ),
                Dictionary(
                    "win-en-gb",
                    _windows_spelling_path("en-GB"),
                    DictionaryFormat.TEXT,
                    encoding="utf-16-le",
                    bom=True,
                    subset=subset_english,
                ),
            ]
        )
    elif is_macos():
        for name, path in macos_dictionary_paths():
            dictionaries.append(Dictionary(name, str(path), DictionaryFormat.TEXT))
    return dictionaries


def _discover_sublime() -> List[Dictionary]:
    sublime_dict = sublime_packages_dir() / SUBLIME_PACKAGE / "Preferences.sublime-settings"
    return [Dictionary("sublime", str(sublime_dict), DictionaryFormat.JSON)]


def _discover_editors() -> List[Dictionary]:
    return [
        Dictionary(f"editor:{editor}", str(path), DictionaryFormat.TEXT)
        for editor, path in editor_dict_paths()
    ]


def _discover_chrome() -> List[Dictionary]:
    return [
        Dictionary(f"chrome:{profile}", str(path), DictionaryFormat.CHROME)
        for profile, path in chrome_dict_paths()
    ]


def _discover_edge() -> List[Dictionary]:
    return [
        Dictionary(f"edge:{profile}", str(path), DictionaryFormat.CHROME)
        for profile, path in edge_dict_paths()
    ]


def _discover_brave() -> List[Dictionary]:
    return [
        Dictionary(f"brave:{profile}", str(path), DictionaryFormat.CHROME)
        for profile, path in brave_dict_paths()
    ]


def _discover_vivaldi() -> List[Dictionary]:
    return [
        Dictionary(f"vivaldi:{profile}", str(path), DictionaryFormat.CHROME)
        for profile, path in vivaldi_dict_paths()
    ]


def _discover_firefox() -> List[Dictionary]:
    return [
        Dictionary(f"firefox:{profile}", str(path), DictionaryFormat.TEXT)
        for profile, path in firefox_dict_paths()
    ]


def _discover_neovim() -> List[Dictionary]:
    return [
        Dictionary(name, str(path), DictionaryFormat.TEXT) for name, path in neovim_dict_paths()
    ]


def _discover_jetbrains() -> List[Dictionary]:
    return [
        Dictionary(f"jetbrains:{product}", str(path), DictionaryFormat.JETBRAINS)
        for product, path in jetbrains_dict_paths()
    ]


def _discover_hunspell() -> List[Dictionary]:
    return [
        Dictionary(f"hunspell:{label}", str(path), DictionaryFormat.HUNSPELL)
        for label, path in hunspell_dict_paths()
    ]


def _discover_obsidian() -> List[Dictionary]:
    return [
        Dictionary(name, str(path), DictionaryFormat.CHROME) for name, path in obsidian_dict_paths()
    ]


def _discover_libreoffice() -> List[Dictionary]:
    return [
        Dictionary(f"libreoffice:{label}", str(path), DictionaryFormat.TEXT)
        for label, path in libreoffice_dict_paths()
    ]


def _optional_dictionary_sources() -> tuple[DictionarySource, ...]:
    """Build optional sources at call time so tests can patch enable_* helpers."""
    return (
        DictionarySource("editors", enable_editors, _discover_editors),
        DictionarySource("chrome", enable_chrome, _discover_chrome),
        DictionarySource("edge", enable_edge, _discover_edge),
        DictionarySource("brave", enable_brave, _discover_brave),
        DictionarySource("vivaldi", enable_vivaldi, _discover_vivaldi),
        DictionarySource("firefox", enable_firefox, _discover_firefox),
        DictionarySource("neovim", enable_neovim, _discover_neovim),
        DictionarySource("jetbrains", enable_jetbrains, _discover_jetbrains),
        DictionarySource("hunspell", enable_hunspell, _discover_hunspell),
        DictionarySource("obsidian", enable_obsidian, _discover_obsidian),
        DictionarySource("libreoffice", enable_libreoffice, _discover_libreoffice),
    )


def discover_dictionaries(
    settings: dict[str, dict[str, object]] | None = None,
) -> List[Dictionary]:
    if settings is not None:
        bind_active_settings(settings)
    dictionaries = _platform_dictionaries()
    dictionaries.extend(_discover_sublime())
    dictionaries.extend(discover_from_sources(_optional_dictionary_sources()))
    return _dedupe_dictionaries(dictionaries)
