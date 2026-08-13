"""Central product copy for the personal word list and custom dictionary model.

UI-neutral: no TUI framework, argparse, or filesystem imports. Texts must not contain
absolute paths or example words.

Guest style: sentence case, “word list”, spaced em dash, Unicode ellipsis (…).
"""

CANONICAL_WORDLIST_SHORT_DESCRIPTION = (
    "Personal spelling exceptions: names, technical terms, abbreviations, "
    "project-specific words, and other words enabled applications should recognize."
)

CANONICAL_WORDLIST_LONG_DESCRIPTION = (
    "Your personal word list contains spelling exceptions: names, "
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
    "Collect my words merges words found in enabled application custom dictionaries "
    "into your personal word list."
)

PUSH_SCOPE_NOTICE = (
    "Update my apps writes the applicable personal words from your word list to each "
    "enabled application custom dictionary."
)

PUSH_FILTERING_NOTICE = (
    "Most apps receive your full word list.\n"
    "Some platform-specific apps receive an applicable subset."
)

# Short block under Update preview counts (not behind Show details).
PUSH_PREVIEW_CONTEXT = (
    "Most apps get your full word list; some platform apps get a filtered subset.\n"
    "Built-in dictionaries are not inspected — duplicate custom entries are expected."
)

PUSH_REDUNDANCY_NOTICE = (
    "Spell Sync does not inspect applications' built-in dictionaries. Some personal "
    "words may therefore be stored redundantly in an application's custom dictionary. "
    "This intentional redundancy keeps your personal word list consistent across enabled "
    "applications."
)

USER_PROBLEM_STATEMENT = (
    "You teach a browser or editor a personal word — a name, product term, or "
    "abbreviation — then open another app and it is marked as misspelled again."
)

WELCOME_INTRO = (
    "Spell Sync keeps those personal words in one private list on your computer "
    "and copies them into the custom dictionaries of the apps you choose."
)

WELCOME_WHAT_YOU_DO = (
    "Next you will pick a folder and which apps to include. "
    "Every change shows a preview first — nothing runs by itself."
)

SETUP_START_BUTTON_LABEL = "Start here"

REVIEW_AND_UPDATE_LABEL = "Review and update"

REVIEW_AND_UPDATE_HELP = "Collect from apps, then update apps — you confirm each preview."

DASHBOARD_NEXT_STEP = (
    "Next step: open Review and update.\n"
    "That walks you through collecting words from your apps, then updating those apps. "
    "You confirm each preview."
)

DASHBOARD_EMPTY_APPS_CTA = "Next step: open Applications to choose which apps to sync."

DASHBOARD_NO_APPS_LINE = "No applications configured"

COLLECT_WORDS_LABEL = "Collect my words"
COLLECT_WORDS_HELP = (
    "Add custom words from your apps to your personal word list. Nothing is removed."
)

UPDATE_APPS_LABEL = "Update my apps"
UPDATE_APPS_HELP = (
    "Match app dictionaries to your word list. Missing words may be removed from "
    "custom dictionaries — built-in dictionaries are never changed."
)

CHECK_APPS_LABEL = "Check my apps"
CHECK_APPS_HELP = (
    "See which apps are ready and what needs attention "
    "(differences and readiness — not system Health)."
)

HEALTH_BUTTON_HELP = "Paths, permissions, and fixable setup problems."

# CLI verbs remain pull/push; guest copy prefers Collect / Update.
COLLECT_WORDS_TECHNICAL = "Collect my words (Pull)"
UPDATE_APPS_TECHNICAL = "Update my apps (Push)"

PULL_PREVIEW_SAFETY = (
    "These words will be added to your personal word list. Nothing will be removed."
)

PUSH_PREVIEW_SAFETY = (
    "These app dictionaries will be updated. Words missing from your personal list may "
    "be removed from custom dictionaries. Built-in dictionaries are never changed."
)

PUSH_REMOVALS_WARNING = (
    "Removals: some custom words will be deleted from apps because they are no longer "
    "in your personal word list. Review them before confirming."
)

BUILTIN_DICTIONARY_GUARANTEE = (
    "Built-in dictionaries shipped with applications are never read or changed."
)

WELCOME_BUILT_IN_EXCLUSION = BUILTIN_DICTIONARY_GUARANTEE

WHY_THIS_IS_SAFE_SHORT = (
    "Only each app's custom word list is updated — never the built-in dictionary "
    "that ships with the app."
)

WORDLIST_SETUP_HEADING = "Choose the folder for your personal word list"

WORDLIST_SETUP_WHAT_BELONGS = (
    "What belongs here:\n"
    "Names, technical terms, abbreviations, and other personal words you want "
    "your apps to recognize."
)

WORDLIST_SETUP_REDUNDANCY_NOTE = (
    "Some apps may already know a few of these words through their built-in "
    "dictionaries. Keeping them in your list is harmless and keeps apps consistent."
)

WORDLIST_SETUP_RECOMMENDED_BUTTON = "Use selected folder"

# Confirm / run button labels (guest-facing Collect / Update).
COLLECT_CONFIRM_BUTTON = "Collect my words"
UPDATE_CONFIRM_BUTTON = "Update my apps"
UPDATE_REMOVAL_CONFIRM_TOKEN = "REMOVE"
UPDATE_REMOVAL_CONFIRM_PROMPT = "Type REMOVE to continue."

WORDLIST_SETUP_CUSTOM_PATH_HINT = (
    "Or choose another folder below. "
    "Empty field lists home (~/). End a folder with / to browse inside. "
    "Tab applies the highlighted row."
)

# Storage strategy ids used by setup UI (not filesystem paths).
STORAGE_STRATEGY_LOCAL = "local"
STORAGE_STRATEGY_CLOUD = "cloud_folder"
STORAGE_STRATEGY_GIT = "git_remote"

STORAGE_SETUP_HEADING = "How will you keep this word list?"

STORAGE_SETUP_INTRO = (
    "Spell Sync does not sync over the network by itself. "
    "Most people start on this computer — you can move the folder later."
)

STORAGE_SETUP_LOCAL_PRIMARY = "This computer only — continue"

STORAGE_SETUP_MORE_OPTIONS = "Other options…"

STORAGE_SETUP_MORE_INTRO = (
    "Choose how the folder should travel between computers. "
    "Spell Sync still only reads and writes files on disk."
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
        "repo, without Git. Pause sync while confirming Update my apps if two "
        "computers might edit at once."
    ),
    STORAGE_STRATEGY_GIT: (
        "Store the folder in your own private Git repository (recommended data-only "
        "layout: wordlist + config). Keep the repository private: a word list can "
        "reveal names and project terms. A local folder alone is still enough — "
        "Git is optional."
    ),
}

WORDLIST_SETUP_STORAGE_REMINDER = (
    "This path is only the folder on disk. Network sync (if any) comes from your "
    "cloud app or Git remote — not from Spell Sync."
)

CHANGE_WORDLIST_HEADING = "Change word list location"

CHANGE_WORDLIST_HINT = "Points Spell Sync at another wordlist.txt — does not move files."

CHANGE_WORDLIST_BODY = (
    "Points Spell Sync at another wordlist.txt — does not move or copy files.\n\n"
    "To switch approaches (local, synced folder, or Git):\n"
    "1. Copy or move the folder yourself (or clone the repo).\n"
    "2. Enter the new path to wordlist.txt here.\n"
    "3. On another computer: open the same folder, then Review and update."
)

STORAGE_PREVIEW_LABELS: dict[str, str] = {
    STORAGE_STRATEGY_LOCAL: "This computer only (no automatic network sync)",
    STORAGE_STRATEGY_CLOUD: "Synced folder (Dropbox / iCloud / Yandex Disk / …)",
    STORAGE_STRATEGY_GIT: "Private Git remote (you commit and push/pull)",
}

# Guest-facing label for custom-dictionary sync entries (internal code still says "target").
APPLICATIONS_LABEL = "Applications"

# Apps = application families (Applications screen, dashboard "✓ N ready").
# Dictionaries = individual custom dictionary files/profiles (preview rows, push counts).
# Never use "apps" for a dictionary-file count — family and file counts often differ.
DICTIONARY_TABLE_COLUMN = "Dictionary"
DICTIONARIES_TO_UPDATE_LABEL = "Dictionaries to update"

APPLICATIONS_SCOPE_NOTICE = (
    "These are application custom dictionaries. "
    "Built-in application dictionaries are not modified or inspected."
)

# One-line form for compact TUI headers (max ~3 lines).
APPLICATIONS_SCOPE_LINE = "Custom dictionaries only — built-in dictionaries are not modified."

PULL_DIRECTION_LABEL = "Your apps → your word list"

PUSH_DIRECTION_LABEL = "Your word list → your apps"

PULL_PREVIEW_EMPTY = (
    "No new words to collect — everything readable from your apps is already in your list."
)

# Review flow when Collect is empty: the only forward step is Update (not an optional skip).
PULL_PREVIEW_EMPTY_NEXT = "Next: Update my apps."

SKIP_COLLECT_LABEL = "Skip collect"

CONTINUE_TO_UPDATE_APPS_LABEL = "Continue to Update my apps"

# Review flow when Update has nothing to do (or preview failed): sole forward step is summary.
PUSH_PREVIEW_EMPTY_NEXT = "Next: review summary."

FINISH_WITHOUT_UPDATE_LABEL = "Finish without update"

CONTINUE_TO_REVIEW_SUMMARY_LABEL = "Continue to review summary"

REVIEW_START_BODY = (
    "Usual path after setup:\n"
    "1. Collect new personal words from your apps (preview first).\n"
    "2. Update your apps from your list (preview first).\n\n"
    "Nothing changes until you confirm."
)

REVIEW_PULL_COMPLETE_BODY = (
    "Collect finished.\n\nYour word list changed. Next step: build a fresh Update my apps preview."
)

REVIEW_SESSION_DONE_MATCHED = (
    "Done. Your apps match your word list for this review.\n\n"
    "When you teach an app a new personal word later, run Review and update again."
)

REVIEW_SESSION_DONE_PARTIAL = (
    "Review finished.\n\n"
    "Some steps were skipped or need attention — check the summary above. "
    "You can run Review and update again anytime."
)

CLI_ROOT_DESCRIPTION = (
    "Synchronize a personal word list with application custom dictionaries. "
    "Built-in dictionaries are not inspected."
)

CLI_PULL_HELP = (
    "Pull (Collect my words): merge words from enabled application custom dictionaries "
    "into your personal word list."
)

CLI_PUSH_HELP = (
    "Push (Update my apps): write personal words from your word list to enabled "
    "application custom dictionaries."
)

CLI_PUSH_REDUNDANCY_EPILOG = (
    "Some words may already be recognized by an application's built-in dictionary. "
    "Spell Sync intentionally does not try to remove this redundancy."
)

DASHBOARD_WORDLIST_LABEL = "Your personal word list"

DASHBOARD_WORDLIST_SUBTITLE = "Personal spelling exceptions"

NARROW_TERMINAL_HINT = (
    "Terminal is smaller than 80 by 24 — showing the compact dashboard. "
    "Widen the window for the full layout."
)


def pull_preview_additions_line(additions: int) -> str:
    if additions == 0:
        return PULL_PREVIEW_EMPTY
    if additions == 1:
        return "1 word from your apps is not in your list yet."
    return f"{additions} words from your apps are not in your list yet."


def pull_completed_summary(additions: int) -> str:
    if additions == 0:
        return "No new personal words were found in application custom dictionaries."
    if additions == 1:
        return "1 personal word was added from application custom dictionaries."
    return f"{additions} personal words were added from application custom dictionaries."


def push_completed_summary(custom_dictionary_count: int) -> str:
    if custom_dictionary_count == 0:
        return "No custom dictionaries were updated from your word list."
    if custom_dictionary_count == 1:
        return "1 custom dictionary was updated from your word list."
    return f"{custom_dictionary_count} custom dictionaries were updated from your word list."


def dictionaries_updated_phrase(count: int) -> str:
    """Short count for Last / history when counting dictionary files, not app families."""
    if count == 1:
        return "1 dictionary updated"
    return f"{count} dictionaries updated"


def dictionaries_skipped_phrase(count: int) -> str:
    if count == 1:
        return "1 dictionary skipped"
    return f"{count} dictionaries skipped"


def push_completed_with_skips_summary(*, written: int, skipped: int) -> str:
    return f"{dictionaries_updated_phrase(written)}, {dictionaries_skipped_phrase(skipped)}."


def apps_changed_phrase(count: int) -> str:
    """Applications-screen toggles (families), not dictionary-file writes."""
    if count == 1:
        return "1 app changed"
    return f"{count} apps changed"


def push_preview_unavailable_message(*, reason: str | None = None) -> str:
    """User-facing push preview failure without raw exit codes."""
    del reason
    return f"× {UPDATE_APPS_LABEL} preview is unavailable right now."


def pull_preview_unavailable_message() -> str:
    return f"× {COLLECT_WORDS_LABEL} preview is unavailable right now."
