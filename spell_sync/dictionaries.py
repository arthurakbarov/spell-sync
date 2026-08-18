"""Local dictionary description and discovery."""

import os
from pathlib import Path

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
    enable_macos_spelling,
    enable_neovim,
    enable_obsidian,
    enable_sublime,
    enable_vivaldi,
    enable_win_spelling,
)
from .dictionary_model import Dictionary, DictionaryFormat
from .dictionary_registry import DictionarySource, discover_from_sources
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
from .runtime_settings import RuntimeSettings
from .words import subset_english, subset_russian

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


def _dedupe_dictionaries(dictionaries: list[Dictionary]) -> list[Dictionary]:
    seen: dict[str, str] = {}
    unique: list[Dictionary] = []
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


def _discover_macos_spelling() -> list[Dictionary]:
    if not is_macos():
        return []
    return [
        Dictionary(name, str(path), DictionaryFormat.TEXT)
        for name, path in macos_dictionary_paths()
    ]


def _discover_win_spelling() -> list[Dictionary]:
    if not is_windows():
        return []
    return [
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


def _discover_sublime() -> list[Dictionary]:
    # Vocabulary only — Packages/SpellSync/Preferences.sublime-settings.
    # Do not write Packages/User/Preferences.sublime-settings (editor UI lives there;
    # a User added_words list would override this package layer).
    sublime_dict = sublime_packages_dir() / SUBLIME_PACKAGE / "Preferences.sublime-settings"
    return [Dictionary("sublime", str(sublime_dict), DictionaryFormat.JSON)]


def _discover_editors() -> list[Dictionary]:
    return [
        Dictionary(f"editor:{editor}", str(path), DictionaryFormat.TEXT)
        for editor, path in editor_dict_paths()
    ]


def _discover_chrome() -> list[Dictionary]:
    return [
        Dictionary(f"chrome:{profile}", str(path), DictionaryFormat.CHROME)
        for profile, path in chrome_dict_paths()
    ]


def _discover_edge() -> list[Dictionary]:
    return [
        Dictionary(f"edge:{profile}", str(path), DictionaryFormat.CHROME)
        for profile, path in edge_dict_paths()
    ]


def _discover_brave() -> list[Dictionary]:
    return [
        Dictionary(f"brave:{profile}", str(path), DictionaryFormat.CHROME)
        for profile, path in brave_dict_paths()
    ]


def _discover_vivaldi() -> list[Dictionary]:
    return [
        Dictionary(f"vivaldi:{profile}", str(path), DictionaryFormat.CHROME)
        for profile, path in vivaldi_dict_paths()
    ]


def _discover_firefox() -> list[Dictionary]:
    return [
        Dictionary(f"firefox:{profile}", str(path), DictionaryFormat.TEXT)
        for profile, path in firefox_dict_paths()
    ]


def _discover_neovim() -> list[Dictionary]:
    return [
        Dictionary(name, str(path), DictionaryFormat.TEXT) for name, path in neovim_dict_paths()
    ]


def _discover_jetbrains() -> list[Dictionary]:
    return [
        Dictionary(f"jetbrains:{product}", str(path), DictionaryFormat.JETBRAINS)
        for product, path in jetbrains_dict_paths()
    ]


def _discover_hunspell() -> list[Dictionary]:
    return [
        Dictionary(f"hunspell:{label}", str(path), DictionaryFormat.HUNSPELL)
        for label, path in hunspell_dict_paths()
    ]


def _discover_obsidian() -> list[Dictionary]:
    return [
        Dictionary(name, str(path), DictionaryFormat.CHROME) for name, path in obsidian_dict_paths()
    ]


def _discover_libreoffice() -> list[Dictionary]:
    return [
        Dictionary(f"libreoffice:{label}", str(path), DictionaryFormat.TEXT)
        for label, path in libreoffice_dict_paths()
    ]


def _optional_dictionary_sources(
    settings: RuntimeSettings,
) -> tuple[DictionarySource, ...]:
    """Build optional sources at call time so tests can patch enable_* helpers."""
    return (
        DictionarySource("sublime", lambda: enable_sublime(settings=settings), _discover_sublime),
        DictionarySource("editors", lambda: enable_editors(settings=settings), _discover_editors),
        DictionarySource("chrome", lambda: enable_chrome(settings=settings), _discover_chrome),
        DictionarySource("edge", lambda: enable_edge(settings=settings), _discover_edge),
        DictionarySource("brave", lambda: enable_brave(settings=settings), _discover_brave),
        DictionarySource("vivaldi", lambda: enable_vivaldi(settings=settings), _discover_vivaldi),
        DictionarySource("firefox", lambda: enable_firefox(settings=settings), _discover_firefox),
        DictionarySource("neovim", lambda: enable_neovim(settings=settings), _discover_neovim),
        DictionarySource(
            "jetbrains",
            lambda: enable_jetbrains(settings=settings),
            _discover_jetbrains,
        ),
        DictionarySource(
            "hunspell",
            lambda: enable_hunspell(settings=settings),
            _discover_hunspell,
        ),
        DictionarySource(
            "obsidian",
            lambda: enable_obsidian(settings=settings),
            _discover_obsidian,
        ),
        DictionarySource(
            "libreoffice",
            lambda: enable_libreoffice(settings=settings),
            _discover_libreoffice,
        ),
        DictionarySource(
            "macos_spelling",
            lambda: enable_macos_spelling(settings=settings),
            _discover_macos_spelling,
        ),
        DictionarySource(
            "win_spelling",
            lambda: enable_win_spelling(settings=settings),
            _discover_win_spelling,
        ),
    )


def discover_dictionaries(
    settings: RuntimeSettings,
    *,
    apply_exclusions: bool = True,
) -> list[Dictionary]:
    """Discover application custom dictionary files for Pull and Push.

    Returns paths to user-maintained custom dictionary storage only. Built-in
    language dictionaries and application spell-check lexicons are not discovered
    or inspected.

    When ``apply_exclusions`` is true (default), names listed in
    ``[dictionaries].excluded`` are omitted while their family flag stays on.
    Setup / Applications probing passes ``apply_exclusions=False`` so excluded
    dictionaries remain visible for toggles.
    """
    found = _dedupe_dictionaries(discover_from_sources(_optional_dictionary_sources(settings)))
    if not apply_exclusions:
        return found
    excluded = settings.dictionaries.excluded
    if not excluded:
        return found
    return [dictionary for dictionary in found if dictionary.name not in excluded]
