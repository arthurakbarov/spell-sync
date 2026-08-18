"""Central product copy for the personal word list and custom dictionary model.

UI-neutral: no TUI framework, argparse, or filesystem imports. Texts must not contain
absolute paths or example words.

Guest style: sentence case, "word list", spaced em dash, ASCII ellipsis (...).
"""

from collections.abc import Iterable, Sequence

from .field_blocks import format_aligned_fields

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
    "Next you will pick a folder and which apps to include, then you can add a "
    "personal word. Every change shows a preview first — nothing runs by itself."
)

SETUP_START_BUTTON_LABEL = "Start here"

REVIEW_AND_UPDATE_LABEL = "Review and update"

REVIEW_AND_UPDATE_HELP = "Collect from apps, then update apps — you confirm each preview."

DASHBOARD_NEXT_STEP = (
    "Next step: add a personal word (or Collect from apps), then Update my apps.\n"
    "Review and update walks both steps with a preview before each change."
)

DASHBOARD_EMPTY_WORDLIST_CTA = (
    "Next step: Add words to my list (or Collect from apps), then Update my apps.\n"
    "Update stops while the list is empty."
)

# Shared after successful Update (standalone report, review Done, Add-words next).
UPDATE_VERIFY_HINT = (
    "Some apps need a restart or reload before they show new words. "
    "Open an enabled app and check that your word is accepted."
)

# After Update when an editor dictionary was written (VS Code / Cursor family).
EDITOR_WIRE_HINT = (
    "If you use VS Code or Cursor, point your spell-check extension at "
    "spell-sync-words.txt once, then reload the editor window."
)

EMPTY_WORDLIST_WARN = (
    "word list is empty — Update my apps will stop until you Add words (or Collect from apps)."
)

RECOVERY_NONE_FOUND = "No interrupted update was found."
RECOVERY_CLEANUP_REMAINING = "The update finished, but recovery files remain."
RECOVERY_INERT_WARNING = "No file writes started for this update. Discard records to unlock writes."
RECOVERY_INERT_DETAIL = "No file writes started — discard interrupted-update records to unlock."
RECOVERY_DISCARD_LABEL = "Discard records"
RECOVERY_CLEANUP_LABEL = "Clean up leftover files"
RECOVERY_CONFIRM_RECOVER_BUTTON = "Recover files"
RECOVERY_FIELD_RECORD = "Record"
PULL_FAILED_MESSAGE = "Collect my words could not complete."
PUSH_FAILED_MESSAGE = "Update my apps could not complete."
WORD_LIST_UNREADABLE_STATUS = "Your word list could not be read."
WORD_LIST_COUNT_UNREADABLE = "could not be read"
FULL_WORD_LIST_FILTER_LABEL = "Full personal word list"

CLI_ADD_HELP = (
    "Add words to your personal word list (one argument per word). "
    "Then preview with plan and write with push, or use Update my apps in the TUI."
)

ADD_WORDS_LABEL = "Add words to my list"
ADD_WORDS_HELP = (
    "Type names or terms into your personal word list, then Continue to Update my apps."
)

FIRST_WIN_HEADING = "What do you want to do first?"
FIRST_WIN_INTRO = "Setup is done. Pick how you want to get your first personal word into your apps."
FIRST_WIN_ADD_LABEL = "Add words to my list"
FIRST_WIN_COLLECT_LABEL = "Collect, then Update my apps"
FIRST_WIN_DASHBOARD_LABEL = "Go to dashboard"
FIRST_WIN_ADD_HINT = "Best when the word is not in any app yet."
FIRST_WIN_COLLECT_HINT = "Best when an app already knows the word."

ADD_WORDS_HEADING = "Add words to my list"
ADD_WORDS_INTRO = (
    "One word per line (no spaces). These are added to your personal word list only — "
    "apps change after you confirm Update my apps."
)
ADD_WORDS_SAVE_LABEL = "Save to my list"
ADD_WORDS_EMPTY_ERROR = "Enter at least one word."
ADD_WORDS_NO_PROJECT = "Open a project with a word list first."
ADD_WORDS_BLOCKED = "Add words blocked — check Health or finish Recovery first."
ADD_WORDS_WRITE_FAILED = "Could not write the word list."
ADD_WORDS_NONE_NEW = "Those words are already in your list (or could not be used)."
ADD_WORDS_SAVED_NEXT = (
    "Saved to your word list.\n\n"
    "Next: Update my apps so enabled apps receive these words (preview first).\n"
    f"{UPDATE_VERIFY_HINT}"
)

DASHBOARD_EMPTY_APPS_CTA = "Next step: open Applications to choose which apps to sync."

DASHBOARD_NO_APPS_LINE = "No applications configured"

COLLECT_WORDS_LABEL = "Collect my words"
COLLECT_WORDS_HELP = (
    "Add custom words from your apps to your personal word list. Nothing is removed."
)

REVIEW_EXTRA_WORDS_LABEL = "Review extra words"
REVIEW_EXTRA_WORDS_HELP = (
    "Choose which app-only words to add to your word list, then remove the rest from apps."
)
EXTRA_WORDS_HEADING = "Extra words"
EXTRA_WORDS_KEEP_HINT = (
    "Checked words are added to your word list. Next you can remove leftovers from apps."
)
EXTRA_WORDS_WIPE_HEADING = "Remaining extra words"
EXTRA_WORDS_WIPE_HINT = (
    "Checked words are removed from every app that has them. "
    "Clear the checks first if you want to leave them in apps."
)
EXTRA_WORDS_FIND_LABEL = "Find extra words"
EXTRA_WORDS_TOGGLE_ALL_LABEL = "Select all / clear"
EXTRA_WORDS_ADD_LABEL = "Add selected to my list"
EXTRA_WORDS_SKIP_TO_REMOVE_LABEL = "Skip to remove from apps"
EXTRA_WORDS_CONTINUE_TO_REMOVE_LABEL = "Continue to remove from apps"
EXTRA_WORDS_REMOVE_LABEL = "Remove selected from apps"
EXTRA_WORDS_EMPTY = "No extra words. Enabled apps have nothing beyond your word list."
EXTRA_WORDS_REMAINING_EMPTY = "No remaining extra words."
EXTRA_WORDS_UNAVAILABLE = "Extra words are unavailable right now."
EXTRA_WORDS_WIPE_CONFLICT = (
    "Apps or project settings changed after the scan. Find extra words again."
)
EXTRA_WORDS_WIPE_WRITE_FAILED = "Could not update one or more app dictionaries."
EXTRA_WORDS_WIPE_EMPTY = "Left remaining extra words in apps."
EXTRA_WORDS_WIPE_DONE = "Removed selected extra words from apps."
EXTRA_WORDS_ADDED = "Added selected words to your word list."
EXTRA_WORDS_DONE_HINT = "Next: Update my apps so enabled apps match your list (preview first)."
EXTRA_WORDS_WRITE_BLOCKED = "Writes are blocked. Resolve recovery or blocking issues first."


def extra_words_page_line(current: int, total: int, count: int) -> str:
    return f"Page {current} of {total} ({count} words)"


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

HEALTH_LABEL = "Health"
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
# Preview keeps Collect my words (no write). Confirm names the write.
# "Add these" keeps this distinct from Add words to my list (type-in).
COLLECT_CONFIRM_BUTTON = "Add these to my list"
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

STORAGE_SETUP_MORE_OPTIONS = "Other options..."

STORAGE_SETUP_MORE_INTRO = (
    "Choose how the folder should travel between computers. "
    "Spell Sync still only reads and writes files on disk."
)

STORAGE_STRATEGY_LABELS: dict[str, str] = {
    STORAGE_STRATEGY_LOCAL: "This computer only",
    STORAGE_STRATEGY_CLOUD: "Synced folder (Dropbox, iCloud, Yandex Disk, ...)",
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
    STORAGE_STRATEGY_CLOUD: "Synced folder (Dropbox / iCloud / Yandex Disk / ...)",
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

# Setup Applications screen: goal-led selection (destination apps first).
SETUP_APPS_GOAL_LINE = (
    "Enable apps where you want words to work. Collect later from apps that already know them."
)

PULL_DIRECTION_LABEL = "Your apps → your word list"

PUSH_DIRECTION_LABEL = "Your word list → your apps"

PULL_PREVIEW_EMPTY = (
    "No new words to collect — everything readable from your apps is already in your list."
)

PULL_PREVIEW_EMPTY_LIST_EMPTY = (
    "No words to collect from your apps, and your personal list is empty.\n"
    "Add words to your list before Update my apps."
)

# Review flow when Collect is empty: the only forward step is Update (not an optional skip).
PULL_PREVIEW_EMPTY_NEXT = "Next: Update my apps."

# Empty list + empty Collect: do not send the guest into Update (it will abort).
PULL_PREVIEW_EMPTY_LIST_EMPTY_NEXT = "Next: Add words to your list."

SKIP_COLLECT_LABEL = "Skip collect"

CONTINUE_TO_UPDATE_APPS_LABEL = "Continue to Update my apps"

# Review flow when Update has nothing to do (or preview failed): sole forward step is summary.
PUSH_PREVIEW_EMPTY_NEXT = "Next: review summary."

FINISH_WITHOUT_UPDATE_LABEL = "Finish without update"

CONTINUE_TO_REVIEW_SUMMARY_LABEL = "Continue to review summary"

REVIEW_START_BODY = (
    "Usual path after setup:\n"
    "1. Add words to your list, or Collect words already stored in your apps "
    "(preview first).\n"
    "2. Update your apps from your list (preview first).\n\n"
    "Nothing changes until you confirm."
)

REVIEW_PULL_COMPLETE_BODY = (
    "Collect finished.\n\nYour word list changed. Next: Update my apps (preview first)."
)


def update_followup_hint(*, editors_updated: bool = False) -> str:
    if editors_updated:
        return f"{UPDATE_VERIFY_HINT}\n\n{EDITOR_WIRE_HINT}"
    return UPDATE_VERIFY_HINT


def dictionary_name_is_editor(name: str) -> bool:
    family = name.split(":", 1)[0]
    return family in {"editor", "editors"}


def written_includes_editors(names: Iterable[str]) -> bool:
    return any(dictionary_name_is_editor(name) for name in names)


def review_session_done_matched(*, editors_updated: bool = False) -> str:
    return (
        "Custom dictionaries were updated to match your word list for this review.\n\n"
        f"{update_followup_hint(editors_updated=editors_updated)}\n\n"
        "When you teach an app a new personal word later, run Review and update again."
    )


REVIEW_SESSION_DONE_MATCHED = review_session_done_matched()

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

CLI_STATUS_HELP = "compare your word list to app dictionaries"
CLI_PLAN_HELP = "preview Update my apps without writing"
CLI_RECOVER_HELP = "restore an interrupted update"
CLI_INIT_HELP = "create a personal word list and project config"
INIT_CLI_TITLE = "init: create a personal word list and project config"
INIT_DESCRIPTION = "Create a local Spell Sync project folder with a word list and config file."

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


def words_count_label(count: int) -> str:
    if count == 1:
        return "1 word"
    return f"{count} words"


def numbered_word_lines(words: Iterable[str]) -> str:
    ordered = sorted(words)
    if not ordered:
        return ""
    width = len(str(len(ordered)))
    return "\n".join(f"{index:>{width}}. {word}" for index, word in enumerate(ordered, start=1))


def numbered_word_prefix(index: int, total: int) -> str:
    width = len(str(max(total, 1)))
    return f"{index:>{width}}."


def added_words_status_block(words: Sequence[str]) -> str:
    """Status block for words just saved on Add words."""
    count = len(words)
    if count <= 2:
        return f"Added ({count}): {', '.join(words)}"
    return f"Added ({count}):\n{numbered_word_lines(words)}"


def pull_preview_dictionary_count_lines(*, ready: int, skipped: int) -> tuple[str, ...]:
    return tuple(
        format_aligned_fields(
            [
                ("Dictionaries ready", ready),
                ("Dictionaries skipped", skipped),
            ]
        )
    )


def pull_preview_warning_lines(warnings: Sequence[str]) -> tuple[str, ...]:
    return tuple(f"  ! {warning}" for warning in warnings)


def collect_confirm_add_line(additions: int) -> str:
    if additions == 1:
        return "Add 1 word to your personal word list?"
    return f"Add {additions} words to your personal word list?"


def pull_preview_additions_line(additions: int, *, before_count: int | None = None) -> str:
    if additions == 0:
        if before_count == 0:
            return PULL_PREVIEW_EMPTY_LIST_EMPTY
        return PULL_PREVIEW_EMPTY
    if additions == 1:
        return "1 word from your apps is not in your list yet."
    return f"{additions} words from your apps are not in your list yet."


def pull_preview_empty_next_line(*, before_count: int) -> str:
    if before_count == 0:
        return PULL_PREVIEW_EMPTY_LIST_EMPTY_NEXT
    return PULL_PREVIEW_EMPTY_NEXT


def pull_completed_summary(additions: int) -> str:
    if additions == 0:
        return "No new personal words were found in application custom dictionaries."
    if additions == 1:
        return "1 personal word was added from application custom dictionaries."
    return f"{additions} personal words were added from application custom dictionaries."


def format_pull_word_count_line(
    before: int,
    after: int,
    *,
    skipped_sources: int = 0,
) -> str:
    added = after - before
    line = f"word list: {before} -> {after} (+{added})"
    if skipped_sources <= 0:
        return line
    noun = "source" if skipped_sources == 1 else "sources"
    return f"{line}; skipped {skipped_sources} {noun}"


def push_completed_summary(
    custom_dictionary_count: int,
    *,
    editors_updated: bool = False,
) -> str:
    if custom_dictionary_count == 0:
        return "No custom dictionaries were updated from your word list."
    if custom_dictionary_count == 1:
        base = "1 custom dictionary was updated from your word list."
    else:
        base = f"{custom_dictionary_count} custom dictionaries were updated from your word list."
    return f"{base}\n\n{update_followup_hint(editors_updated=editors_updated)}"


def dictionaries_updated_phrase(count: int) -> str:
    """Short count for Last / history when counting dictionary files, not app families."""
    if count == 1:
        return "1 dictionary updated"
    return f"{count} dictionaries updated"


def dictionaries_skipped_phrase(count: int) -> str:
    if count == 1:
        return "1 dictionary skipped"
    return f"{count} dictionaries skipped"


def push_completed_with_skips_summary(
    *,
    written: int,
    skipped: int,
    editors_updated: bool = False,
) -> str:
    base = f"{dictionaries_updated_phrase(written)}, {dictionaries_skipped_phrase(skipped)}."
    if written <= 0:
        return base
    return f"{base}\n\n{update_followup_hint(editors_updated=editors_updated)}"


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


def recovery_confirm_button(action: str) -> str:
    """Confirm names the write. Preview keeps Recover / cleanup / discard."""
    if action == "discard":
        return RECOVERY_DISCARD_LABEL
    if action == "cleanup":
        return RECOVERY_CLEANUP_LABEL
    return RECOVERY_CONFIRM_RECOVER_BUTTON
