"""Application dictionary paths."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Tuple

from .config import (
    EDITOR_DICT_FILENAME,
    REPO_DIR,
    WORDLIST_FILENAME,
)

PathPair = Tuple[str, Path]


# --- Repository ---

_PROJECT_MARKERS = (
    "spell-sync.toml",
    WORDLIST_FILENAME,
)


def _is_spell_sync_project(directory: Path) -> bool:
    if any((directory / name).exists() for name in _PROJECT_MARKERS):
        return True
    pyproject = directory / "pyproject.toml"
    if pyproject.is_file() and (directory / "spell_sync").is_dir():
        try:
            text = pyproject.read_text(encoding="utf-8")
        except OSError:
            return False
        return 'name = "spell-sync"' in text or "name='spell-sync'" in text
    return False


def project_root() -> Path:
    """Nearest directory with wordlist / spell-sync.toml / spell-sync clone, else cwd."""
    cwd = Path.cwd()
    for directory in (cwd, *cwd.parents):
        if _is_spell_sync_project(directory):
            return directory
    if _is_spell_sync_project(REPO_DIR):
        return REPO_DIR
    return cwd


def wordlist_path() -> Path:
    return project_root() / WORDLIST_FILENAME


def resolve_wordlist_path(explicit: str | None = None) -> Path:
    """Explicit CLI path or default project wordlist location."""
    if explicit:
        return Path(explicit)
    return wordlist_path()


# --- OS ---


def home_dir() -> Path:
    return Path.home()


def is_windows() -> bool:
    return os.name == "nt"


def is_macos() -> bool:
    return sys.platform == "darwin"


def app_support_dir() -> Path:
    if is_windows():
        return Path(os.getenv("APPDATA") or home_dir())
    if is_macos():
        return home_dir() / "Library" / "Application Support"
    return home_dir() / ".config"


def first_existing_dir(candidates: List[Path], default: Path) -> Path:
    for path in candidates:
        if path.is_dir():
            return path
    return default


# --- Sublime Text ---


def _sublime_packages_candidates() -> List[Path]:
    base = app_support_dir()
    if is_macos() or is_windows():
        return [
            base / "Sublime Text" / "Packages",
            base / "Sublime Text 3" / "Packages",
        ]
    return [
        base / "sublime-text" / "Packages",
        base / "sublime-text-3" / "Packages",
        base / "Sublime Text" / "Packages",
    ]


def sublime_packages_dir() -> Path:
    candidates = _sublime_packages_candidates()
    return first_existing_dir(candidates, candidates[0])


def sublime_text_installed() -> bool:
    return any(path.is_dir() for path in _sublime_packages_candidates())


# --- Code editors ---


def editor_user_dirs() -> List[PathPair]:
    base = app_support_dir()
    return [
        ("cursor", base / "Cursor" / "User"),
        ("vscode", base / "Code" / "User"),
    ]


def editor_dict_paths() -> List[PathPair]:
    """spell-sync-words.txt for each detected editor install."""
    found: List[PathPair] = []
    for name, user_dir in editor_user_dirs():
        if user_dir.is_dir():
            found.append((name, user_dir / EDITOR_DICT_FILENAME))
    if not found:
        default_name, default_user = editor_user_dirs()[0]
        found.append((default_name, default_user / EDITOR_DICT_FILENAME))
    return found


def editor_uses_fallback() -> bool:
    return not any(user_dir.is_dir() for _, user_dir in editor_user_dirs())


# --- macOS ---


def macos_dictionary_paths() -> List[PathPair]:
    """
    LocalDictionary: classic path and Group Containers (Sonoma+).

    If the AppleSpell directory exists, push writes to both.
    """
    home = home_dir()
    classic = home / "Library" / "Spelling" / "LocalDictionary"
    group = (
        home
        / "Library"
        / "Group Containers"
        / "group.com.apple.AppleSpell"
        / "Library"
        / "Spelling"
        / "LocalDictionary"
    )
    paths: List[PathPair] = [("macos", classic)]
    if group.parent.is_dir():
        paths.append(("macos-applespell", group))
    return paths


# --- Chrome / Edge (Chromium) ---


def chrome_user_data_dir() -> Path:
    if is_windows():
        local = Path(os.getenv("LOCALAPPDATA") or home_dir())
        return local / "Google" / "Chrome" / "User Data"
    if is_macos():
        return app_support_dir() / "Google" / "Chrome"
    return home_dir() / ".config" / "google-chrome"


def _chromium_dict_paths(base: Path) -> List[PathPair]:
    """Chromium profile Custom Dictionary.txt paths under a User Data directory."""
    if not base.is_dir():
        return []
    profiles: List[PathPair] = []
    try:
        entries = base.iterdir()
    except OSError:
        return []
    for name in sorted(entry.name for entry in entries if entry.is_dir()):
        if name == "Default" or name.startswith("Profile "):
            custom = base / name / "Custom Dictionary.txt"
            profiles.append((name, custom))
    return profiles


def chrome_dict_paths() -> List[PathPair]:
    return _chromium_dict_paths(chrome_user_data_dir())


def edge_user_data_dir() -> Path:
    if is_windows():
        local = Path(os.getenv("LOCALAPPDATA") or home_dir())
        return local / "Microsoft" / "Edge" / "User Data"
    if is_macos():
        return app_support_dir() / "Microsoft Edge"
    return home_dir() / ".config" / "microsoft-edge"


def edge_dict_paths() -> List[PathPair]:
    return _chromium_dict_paths(edge_user_data_dir())


def brave_user_data_dir() -> Path:
    if is_windows():
        local = Path(os.getenv("LOCALAPPDATA") or home_dir())
        return local / "BraveSoftware" / "Brave-Browser" / "User Data"
    if is_macos():
        return app_support_dir() / "BraveSoftware" / "Brave-Browser"
    return home_dir() / ".config" / "BraveSoftware" / "Brave-Browser"


def brave_dict_paths() -> List[PathPair]:
    return _chromium_dict_paths(brave_user_data_dir())


def vivaldi_user_data_dir() -> Path:
    if is_windows():
        local = Path(os.getenv("LOCALAPPDATA") or home_dir())
        return local / "Vivaldi" / "User Data"
    if is_macos():
        return app_support_dir() / "Vivaldi"
    return home_dir() / ".config" / "vivaldi"


def vivaldi_dict_paths() -> List[PathPair]:
    return _chromium_dict_paths(vivaldi_user_data_dir())


# --- Firefox ---


def firefox_profiles_dir() -> Path:
    if is_windows():
        return app_support_dir() / "Mozilla" / "Firefox" / "Profiles"
    if is_macos():
        return app_support_dir() / "Firefox" / "Profiles"
    return home_dir() / ".mozilla" / "firefox"


def firefox_dict_paths() -> List[PathPair]:
    base = firefox_profiles_dir()
    if not base.is_dir():
        return []
    profiles: List[PathPair] = []
    try:
        entries = base.iterdir()
    except OSError:
        return []
    for name in sorted(entry.name for entry in entries if entry.is_dir()):
        persdict = base / name / "persdict.dat"
        if persdict.is_file():
            profiles.append((name, persdict))
    return profiles


# --- Neovim ---


def neovim_data_dir() -> Path:
    if is_windows():
        local = Path(os.getenv("LOCALAPPDATA") or home_dir())
        return local / "nvim-data"
    xdg_data = os.getenv("XDG_DATA_HOME")
    if xdg_data:
        return Path(xdg_data) / "nvim"
    return home_dir() / ".local" / "share" / "nvim"


def neovim_dict_paths() -> List[PathPair]:
    spell_dir = neovim_data_dir() / "site" / "spell"
    return [("nvim-en", spell_dir / "en.utf-8.add")]


# --- JetBrains ---

JETBRAINS_DICT_FILENAMES = ("cachedDictionary.xml", "spellchecker-dictionary.xml")


def jetbrains_config_dir() -> Path:
    if is_windows() or is_macos():
        return app_support_dir() / "JetBrains"
    return home_dir() / ".config" / "JetBrains"


def jetbrains_dict_paths() -> List[PathPair]:
    """Return (product_version, path) for each JetBrains IDE custom dictionary file."""
    base = jetbrains_config_dir()
    if not base.is_dir():
        return []
    pairs: List[PathPair] = []
    try:
        product_dirs = sorted(entry.name for entry in base.iterdir() if entry.is_dir())
    except OSError:
        return []
    for product in product_dirs:
        for filename in JETBRAINS_DICT_FILENAMES:
            path = base / product / "options" / filename
            if path.is_file():
                pairs.append((product, path))
                break
    return pairs


# --- Hunspell ---


def _hunspell_fixed_candidates() -> List[PathPair]:
    """Standard Hunspell personal dictionary locations (include only if the file exists)."""
    home = home_dir()
    candidates: List[PathPair] = [
        ("default", home / ".hunspell_default"),
        ("custom", home / ".local" / "share" / "hunspell" / "custom.dic"),
    ]
    if is_macos():
        candidates.append(("local", home / "Library" / "Spelling" / "local"))
    elif is_windows():
        appdata = app_support_dir()
        candidates.extend(
            [
                ("default", appdata / "hunspell" / "default.dic"),
                ("custom", appdata / "hunspell" / "custom.dic"),
            ]
        )
    return candidates


def hunspell_dict_paths() -> List[PathPair]:
    """Return (label, path) for each existing Hunspell personal dictionary file."""
    pairs: List[PathPair] = []
    for label, path in _hunspell_fixed_candidates():
        if path.is_file():
            pairs.append((label, path))

    config_dir = home_dir() / ".config" / "hunspell"
    if not config_dir.is_dir():
        return pairs
    try:
        for entry in sorted(config_dir.iterdir()):
            if not entry.is_file():
                continue
            if entry.suffix not in (".dic", ".txt", "") and "." in entry.name:
                continue
            pairs.append((entry.name, entry))
    except OSError:
        pass
    return pairs


# --- LibreOffice ---


def libreoffice_user_dir() -> Path:
    if is_windows() or is_macos():
        return app_support_dir() / "LibreOffice" / "4" / "user"
    return home_dir() / ".config" / "libreoffice" / "4" / "user"


def libreoffice_dict_paths() -> List[PathPair]:
    """Personal wordbook (standard.dic) when LibreOffice has created it."""
    wordbook = libreoffice_user_dir() / "wordbook" / "standard.dic"
    if wordbook.is_file():
        return [("libreoffice", wordbook)]
    return []


# --- Obsidian ---


def obsidian_dict_path() -> Path:
    return app_support_dir() / "obsidian" / "Custom Dictionary.txt"


def obsidian_dict_paths() -> List[PathPair]:
    """App-level Obsidian custom dictionary (Chrome-compatible format)."""
    path = obsidian_dict_path()
    if path.is_file() or path.parent.is_dir():
        return [("obsidian", path)]
    return []
