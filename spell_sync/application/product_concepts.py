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
    "Push writes the canonical personal wordlist to enabled application custom dictionaries."
)

PUSH_REDUNDANCY_NOTICE = (
    "Spell Sync does not inspect built-in dictionaries. Some personal words may "
    "be stored redundantly in an application's custom dictionary. "
    "This intentional redundancy keeps enabled applications consistent."
)

WELCOME_INTRO = (
    "Spell Sync keeps one canonical list of your personal spelling exceptions "
    "synchronized with application custom dictionaries."
)

WELCOME_BUILT_IN_EXCLUSION = "It does not inspect or copy applications' built-in dictionaries."

WORDLIST_SETUP_HEADING = "Choose the canonical personal wordlist"

WORDLIST_SETUP_WHAT_BELONGS = (
    "What belongs here?\n\n"
    "Names, technical terms, abbreviations, project-specific words, and other "
    "personal words you want enabled applications to recognize."
)

WORDLIST_SETUP_REDUNDANCY_NOTE = (
    "Some applications may already recognize some of these words through their "
    "built-in dictionaries. Keeping them here is harmless and makes the personal "
    "list consistent across applications."
)

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
    "Spell Sync will review application custom dictionaries first,\n"
    "then prepare a fresh wordlist-to-applications preview.\n"
    "Nothing changes without confirmation."
)

CLI_ROOT_DESCRIPTION = (
    "Synchronize a canonical personal wordlist with application custom dictionaries. "
    "Built-in dictionaries are not inspected."
)

CLI_PULL_HELP = (
    "Pull personal words from enabled application custom dictionaries into the canonical wordlist."
)

CLI_PUSH_HELP = "Push the canonical personal wordlist to enabled application custom dictionaries."

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
        return "The canonical personal wordlist was not written to custom dictionaries."
    noun = "dictionary" if custom_dictionary_count == 1 else "dictionaries"
    return (
        f"The canonical personal wordlist was written to {custom_dictionary_count} custom {noun}."
    )
