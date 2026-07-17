"""spell-sync configuration."""

from __future__ import annotations

from pathlib import Path

from .settings import (
    dictionary_flag,
    io_int,
    load_user_settings,
    neovim_flag,
    push_flag,
    push_int,
)

# --- Filenames ---

WORDLIST_FILENAME = "wordlist.txt"
WHITELIST_FILENAME = "lint-whitelist.txt"
EDITOR_DICT_FILENAME = "spell-sync-words.txt"
SUBLIME_PACKAGE = "SpellSync"
CHROME_CHECKSUM_PREFIX = "checksum_v1 = "

# --- Lint ---

SHORT_WARN_LEN = 2

# --- Push safety ---

# Abort push when the wordlist is tiny but local dictionaries are much larger (run pull first).
PUSH_GUARD_WORDLIST_MAX = 10
PUSH_GUARD_LOCAL_MIN = 20

# Prompt before a push would remove more than this many words from one dictionary.
PUSH_MAX_REMOVALS_WITHOUT_CONFIRM_DEFAULT = 50

# Rotating .bak backups before dictionary overwrite (0 = disabled, 1 = single .bak only).
BACKUP_KEEP_DEFAULT = 3

# Default watch/automation pull interval when enabled (minutes).
AUTOMATION_IMPORT_INTERVAL_DEFAULT = 60

# --- CLI ---

CONFIRM_YES = frozenset({"y", "yes"})

# macOS: the terminal app running spell-sync may need Full Disk Access for AppleSpell paths.
TCC_ACCESS_HINT = "(Terminal / Full Disk Access?)"
MACOS_APPLESPELL_FDA_HINT = (
    "macos-applespell unreadable — grant Full Disk Access to your terminal app: "
    "System Settings → Privacy & Security → Full Disk Access. "
    "push skips AppleSpell but other dictionaries can still be updated."
)

# --- Package paths ---

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_DIR = PACKAGE_DIR.parent


# --- Dictionary flags (spell-sync.toml → [dictionaries], reload on every call) ---


def enable_editors() -> bool:
    return dictionary_flag(load_user_settings(), "editors", True)


def enable_chrome() -> bool:
    return dictionary_flag(load_user_settings(), "chrome", True)


def enable_edge() -> bool:
    return dictionary_flag(load_user_settings(), "edge", True)


def enable_brave() -> bool:
    return dictionary_flag(load_user_settings(), "brave", True)


def enable_vivaldi() -> bool:
    return dictionary_flag(load_user_settings(), "vivaldi", True)


def enable_firefox() -> bool:
    return dictionary_flag(load_user_settings(), "firefox", True)


def enable_neovim() -> bool:
    return dictionary_flag(load_user_settings(), "neovim", True)


def enable_jetbrains() -> bool:
    return dictionary_flag(load_user_settings(), "jetbrains", True)


def enable_hunspell() -> bool:
    return dictionary_flag(load_user_settings(), "hunspell", True)


def enable_obsidian() -> bool:
    return dictionary_flag(load_user_settings(), "obsidian", True)


def enable_libreoffice() -> bool:
    return dictionary_flag(load_user_settings(), "libreoffice", True)


def neovim_mkspell_after_push() -> bool:
    return neovim_flag("mkspell_after_push", False)


def push_guard_wordlist_max() -> int:
    return push_int("guard_wordlist_max", PUSH_GUARD_WORDLIST_MAX)


def push_guard_local_min() -> int:
    return push_int("guard_local_min", PUSH_GUARD_LOCAL_MIN)


def push_strict_enabled() -> bool:
    return push_flag("strict", False)


def push_max_removals_without_confirm() -> int:
    """Manual push warns or prompts when removals exceed this."""
    return push_int(
        "max_removals_without_confirm",
        PUSH_MAX_REMOVALS_WITHOUT_CONFIRM_DEFAULT,
    )


def backup_keep_count() -> int:
    return max(0, io_int("backup_keep", BACKUP_KEEP_DEFAULT))
