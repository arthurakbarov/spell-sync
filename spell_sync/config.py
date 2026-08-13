"""spell-sync configuration."""

from pathlib import Path

from .runtime_settings import RuntimeSettings

# --- Filenames ---

WORDLIST_FILENAME = "wordlist.txt"
WHITELIST_FILENAME = "lint-whitelist.txt"
EDITOR_DICT_FILENAME = "spell-sync-words.txt"
SUBLIME_PACKAGE = "SpellSync"
CHROME_CHECKSUM_PREFIX = "checksum_v1 = "

# --- Push safety ---

# Abort push when the wordlist is tiny but local dictionaries are much larger
# (collect words / pull first).
PUSH_GUARD_WORDLIST_MAX = 10
PUSH_GUARD_LOCAL_MIN = 20

# Prompt before a push would remove more than this many words from one dictionary.
# Also used as the TUI "small delta" ceiling when listing push additions for review
# (larger per-app dumps, e.g. first sync into a new dictionary, are omitted).
PUSH_MAX_REMOVALS_WITHOUT_CONFIRM_DEFAULT = 50
PUSH_SMALL_DELTA_REVIEW_MAX = PUSH_MAX_REMOVALS_WITHOUT_CONFIRM_DEFAULT

# Rotating .bak backups before dictionary overwrite (0 = disabled, 1 = single .bak only).
BACKUP_KEEP_DEFAULT = 3

# --- CLI ---

# Human-mode terminal lines (via log.py). Soft-wrap at this width inclusive.
CLI_OUTPUT_WIDTH = 100
CLI_WRAP_CONTINUATION_INDENT = 2

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

# --- Dictionary flags (spell-sync.toml → [dictionaries]) ---


def enable_editors(*, settings: RuntimeSettings) -> bool:
    return settings.dictionaries.editors


def enable_chrome(*, settings: RuntimeSettings) -> bool:
    return settings.dictionaries.chrome


def enable_edge(*, settings: RuntimeSettings) -> bool:
    return settings.dictionaries.edge


def enable_brave(*, settings: RuntimeSettings) -> bool:
    return settings.dictionaries.brave


def enable_vivaldi(*, settings: RuntimeSettings) -> bool:
    return settings.dictionaries.vivaldi


def enable_firefox(*, settings: RuntimeSettings) -> bool:
    return settings.dictionaries.firefox


def enable_neovim(*, settings: RuntimeSettings) -> bool:
    return settings.dictionaries.neovim


def enable_sublime(*, settings: RuntimeSettings) -> bool:
    return settings.dictionaries.sublime


def enable_jetbrains(*, settings: RuntimeSettings) -> bool:
    return settings.dictionaries.jetbrains


def enable_hunspell(*, settings: RuntimeSettings) -> bool:
    return settings.dictionaries.hunspell


def enable_obsidian(*, settings: RuntimeSettings) -> bool:
    return settings.dictionaries.obsidian


def enable_libreoffice(*, settings: RuntimeSettings) -> bool:
    return settings.dictionaries.libreoffice


def enable_macos_spelling(*, settings: RuntimeSettings) -> bool:
    return settings.dictionaries.macos_spelling


def enable_win_spelling(*, settings: RuntimeSettings) -> bool:
    return settings.dictionaries.win_spelling


def neovim_mkspell_after_push(*, settings: RuntimeSettings) -> bool:
    return settings.neovim.mkspell_after_push


def push_guard_wordlist_max(*, settings: RuntimeSettings) -> int:
    return settings.push.guard_wordlist_max


def push_guard_local_min(*, settings: RuntimeSettings) -> int:
    return settings.push.guard_local_min


def push_strict_enabled(*, settings: RuntimeSettings) -> bool:
    return settings.push.strict


def push_max_removals_without_confirm(*, settings: RuntimeSettings) -> int:
    """Manual push warns or prompts when removals exceed this."""
    return settings.push.max_removals_without_confirm


def backup_keep_count(*, settings: RuntimeSettings) -> int:
    return settings.io.backup_keep
