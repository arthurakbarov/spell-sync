"""Central product copy for the canonical wordlist and custom dictionary model.

UI-neutral: no TUI framework, argparse, or filesystem imports. Texts must not contain
user paths or example words.
"""

from __future__ import annotations

CANONICAL_WORDLIST_SHORT_DESCRIPTION = (
    "Personal spelling exceptions: names, technical terms, abbreviations, "
    "project-specific words, and other words enabled applications should recognize."
)

CANONICAL_WORDLIST_LONG_DESCRIPTION = (
    "The canonical wordlist contains your personal spelling exceptions: names, "
    "technical terms, abbreviations, project-specific words, and other words you "
    "want enabled applications to recognize.\n\n"
    "It holds the personal words you collected explicitly or pulled from application "
    "custom dictionaries. It is not a copy of application built-in dictionaries."
)

CUSTOM_DICTIONARY_SCOPE_NOTICE = (
    "Spell Sync synchronizes application custom dictionaries. "
    "It does not inspect the built-in dictionaries shipped with applications."
)

PULL_SCOPE_NOTICE = (
    "Pull merges words found in enabled application custom dictionaries "
    "into the canonical wordlist."
)

PUSH_SCOPE_NOTICE = (
    "Push writes the applicable personal words from the canonical wordlist to each "
    "enabled application custom dictionary.\n\n"
    "Most targets receive the full canonical wordlist. Some platform-specific targets "
    "apply language- or format-specific filtering."
)

PUSH_FILTERING_NOTICE = (
    "Most targets receive the full canonical wordlist.\n"
    "Some platform-specific targets receive an applicable subset."
)

PUSH_REDUNDANCY_NOTICE = (
    "Spell Sync does not inspect applications' built-in dictionaries. Some personal "
    "words may therefore be stored redundantly in an application's custom dictionary. "
    "This intentional redundancy keeps your personal wordlist consistent across enabled "
    "applications."
)

PUSH_REDUNDANCY_PREVIEW_NOTICE = (
    "Built-in dictionaries are not inspected. Some personal words may be stored "
    "redundantly in a custom dictionary; this is expected."
)

USER_PROBLEM_STATEMENT = (
    "You teach a browser or editor a personal word — a name, product term, or "
    "abbreviation — then open another app and it is marked as misspelled again."
)

WELCOME_INTRO = (
    "Spell Sync keeps those personal words in one private list on your computer "
    "and helps you copy them into the custom dictionaries of supported apps."
)

WELCOME_WHAT_YOU_DO = (
    "You only need to: choose how to keep your list (this computer, a synced folder, "
    "or a private Git remote), pick the folder, pick which apps to include, then use "
    "Review and update when you want changes. Every change shows a preview first — "
    "nothing runs by itself."
)

SETUP_START_BUTTON_LABEL = "Start here"

REVIEW_AND_UPDATE_LABEL = "Review and update"

REVIEW_AND_UPDATE_HELP = (
    "Guided path: collect new words from your apps, then update app dictionaries. "
    "You confirm each step after a preview."
)

COLLECT_WORDS_LABEL = "Collect my words"
COLLECT_WORDS_HELP = (
    "Add custom words from your apps to your personal word list. Nothing is removed."
)

UPDATE_APPS_LABEL = "Update my apps"
UPDATE_APPS_HELP = (
    "Make enabled app dictionaries match your personal word list. Words missing from "
    "your list may be removed from custom dictionaries. Built-in dictionaries are "
    "never changed."
)

CHECK_APPS_LABEL = "Check my apps"
CHECK_APPS_HELP = "See which apps are ready and whether anything needs attention."

COLLECT_WORDS_TECHNICAL = "Collect my words (Pull)"
UPDATE_APPS_TECHNICAL = "Update my apps (Push)"

PULL_PREVIEW_SAFETY = (
    "These words will be added to your personal word list. Nothing will be removed."
)

PUSH_PREVIEW_SAFETY = (
    "These app dictionaries will be updated. Words missing from your personal list may "
    "be removed from custom dictionaries. Built-in dictionaries are never changed."
)

BUILTIN_DICTIONARY_GUARANTEE = (
    "Built-in dictionaries shipped with applications are never read or changed."
)

WELCOME_BUILT_IN_EXCLUSION = BUILTIN_DICTIONARY_GUARANTEE

WORDLIST_SETUP_HEADING = "Choose the folder for your personal word list"

WORDLIST_SETUP_WHAT_BELONGS = (
    "What belongs in the list?\n\n"
    "Names, technical terms, abbreviations, project-specific words, and other "
    "personal words you want enabled applications to recognize."
)

WORDLIST_SETUP_REDUNDANCY_NOTE = (
    "Some applications may already recognize some of these words through their "
    "built-in dictionaries. Keeping them here is harmless and keeps your personal "
    "wordlist consistent across enabled applications."
)

# Storage strategy ids used by setup UI (not filesystem paths).
STORAGE_STRATEGY_LOCAL = "local"
STORAGE_STRATEGY_CLOUD = "cloud_folder"
STORAGE_STRATEGY_GIT = "git_remote"

STORAGE_SETUP_HEADING = "How will you keep this word list?"

STORAGE_SETUP_INTRO = (
    "Spell Sync does not sync over the network by itself. Pick one approach now — "
    "you can move the folder later with Change word list location."
)

STORAGE_STRATEGY_LABELS: dict[str, str] = {
    STORAGE_STRATEGY_LOCAL: "This computer only",
    STORAGE_STRATEGY_CLOUD: "Synced folder (Dropbox, iCloud, Yandex Disk, …)",
    STORAGE_STRATEGY_GIT: "Private Git remote (GitHub or other)",
}

STORAGE_STRATEGY_HINTS: dict[str, str] = {
    STORAGE_STRATEGY_LOCAL: (
        "Simplest. Use a normal folder on this machine. Copy or move the folder "
        "yourself if you later want another computer or a sync app."
    ),
    STORAGE_STRATEGY_CLOUD: (
        "Put the folder inside Dropbox, iCloud Drive, Yandex Disk, OneDrive, or "
        "similar. Those apps sync files between machines — same idea as a remote "
        "repo, without Git. Pause sync while confirming a Push if two computers "
        "might edit at once. Target choices in spell-sync.toml travel with the folder."
    ),
    STORAGE_STRATEGY_GIT: (
        "Store the folder in your own private Git repository (GitHub is common; "
        "any Git host works). Commit and push/pull the folder yourself — Spell Sync "
        "never pushes for you. Keep the repository private: a word list can reveal "
        "names and project terms."
    ),
}

WORDLIST_SETUP_STORAGE_REMINDER = (
    "This path is only the folder on disk. Network sync (if any) comes from your "
    "cloud app or Git remote — not from Spell Sync."
)

CHANGE_WORDLIST_HEADING = "Change word list location"

CHANGE_WORDLIST_BODY = (
    "Points Spell Sync at another wordlist.txt; does not move or copy files.\n\n"
    "To switch approaches (local ↔ synced folder ↔ Git):\n"
    "1. Copy or move the folder yourself (or clone the repo).\n"
    "2. Enter the new path to wordlist.txt here.\n"
    "3. On another computer: open the same folder, then Review and update.\n\n"
    "Path to wordlist.txt:"
)

STORAGE_PREVIEW_LABELS: dict[str, str] = {
    STORAGE_STRATEGY_LOCAL: "This computer only (no automatic network sync)",
    STORAGE_STRATEGY_CLOUD: "Synced folder (Dropbox / iCloud / Yandex Disk / …)",
    STORAGE_STRATEGY_GIT: "Private Git remote (you commit and push/pull)",
}

TARGETS_SCOPE_NOTICE = (
    "Targets are application custom dictionaries. "
    "Built-in application dictionaries are not modified or inspected."
)

PULL_DIRECTION_LABEL = "Applications → canonical wordlist"

PUSH_DIRECTION_LABEL = "Canonical wordlist → application custom dictionaries"

PULL_PREVIEW_EMPTY = (
    "All readable words from enabled custom dictionaries are already "
    "present in the canonical wordlist."
)

REVIEW_START_BODY = (
    "This is the usual path after setup.\n\n"
    "1. Look for new personal words in your apps (Collect my words).\n"
    "2. Optionally add them to your list after you confirm the preview.\n"
    "3. Prepare an Update my apps preview, then confirm if you want it.\n\n"
    "Nothing changes until you confirm. Built-in dictionaries are never touched."
)

CLI_ROOT_DESCRIPTION = (
    "Synchronize a canonical personal wordlist with application custom dictionaries. "
    "Built-in dictionaries are not inspected."
)

CLI_PULL_HELP = (
    "Pull personal words from enabled application custom dictionaries into the canonical wordlist."
)

CLI_PUSH_HELP = (
    "Push personal words from the canonical wordlist to enabled application custom dictionaries."
)

CLI_PUSH_REDUNDANCY_EPILOG = (
    "Some words may already be recognized by an application's built-in dictionary. "
    "Spell Sync intentionally does not try to remove this redundancy."
)

DASHBOARD_WORDLIST_LABEL = "Canonical personal wordlist"

DASHBOARD_WORDLIST_SUBTITLE = "Personal spelling exceptions"


def pull_preview_additions_line(additions: int) -> str:
    if additions == 0:
        return PULL_PREVIEW_EMPTY
    noun = "word" if additions == 1 else "words"
    return (
        f"{additions} {noun} were found in application custom dictionaries "
        f"but are not yet in the canonical wordlist."
    )


def pull_completed_summary(additions: int) -> str:
    if additions == 0:
        return "No new personal words were found in application custom dictionaries."
    noun = "word" if additions == 1 else "words"
    return f"{additions} personal {noun} were added from application custom dictionaries."


def push_completed_summary(custom_dictionary_count: int) -> str:
    if custom_dictionary_count == 0:
        return "No custom dictionaries were updated from the canonical wordlist."
    noun = "dictionary" if custom_dictionary_count == 1 else "dictionaries"
    return f"{custom_dictionary_count} custom {noun} were updated from the canonical wordlist."
