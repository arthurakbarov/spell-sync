"""Guest-facing strings used from core (no application / TUI imports)."""

EMPTY_WORDLIST_ABORT = (
    "word list is empty — add words with `spell-sync add`, edit wordlist.txt, "
    "or use Add words in the TUI, then retry."
)

EMPTY_WORDLIST_DOCTOR = (
    "word list is empty. Add words with `spell-sync add` "
    "(or Add words in the TUI / edit wordlist.txt), then Update my apps."
)
WORD_LIST_UNREADABLE = "word list is unreadable"
WORD_LIST_NOT_FOUND = "word list not found"
WORD_LIST_WRITE_FAILED = "could not write the word list"
REPORT_ALREADY_EXISTS = "a report already exists at that path"

EXISTING_WORD_LIST_PREFIX = "Existing word list:"
SETUP_WORD_LIST_MISSING = "Personal word list does not exist and creation was not requested."
SETUP_WORD_LIST_UNREADABLE = "word list exists but cannot be read"
SETUP_FILE_EXISTS = "a project file already exists."
SETUP_WRITE_FAILED = "could not create project files."
TARGET_SETTINGS_WRITE_FAILED = "could not write spell-sync.toml."

INIT_ALREADY_EXISTS = "nothing to create — this folder already has a Spell Sync project."
INIT_NEXT_HINT = (
    "next: spell-sync add WORD, then spell-sync plan && spell-sync push "
    "(or Add words / Update in the TUI)"
)
ADD_NEXT_HINT = "Next: spell-sync plan && spell-sync push  (or Update my apps in the TUI)"

INIT_STORAGE_HINT = (
    "optional: keep the folder local, in a synced cloud directory, "
    "or a private Git remote — see README (Personal workspace)"
)


def already_present_detail(words: tuple[str, ...]) -> str:
    return f"Already present: {', '.join(words)}"


def skipped_words_detail(words: tuple[str, ...]) -> str:
    return f"Skipped: {', '.join(words)}"


RECOVER_NONE_FOUND = "no interrupted update found"
RECOVER_NOTHING_TO_RESTORE = "nothing to restore"
RECOVER_DRY_RUN_NOTHING = "recover dry-run: nothing to restore"
RECOVER_DISCARD_PROMPT = "Discard interrupted-update records without restoring files? [y/N] "
RECOVER_DISCARD_ABORTED = (
    "recover aborted — an interrupted update was found that never wrote files. "
    "Pass `--yes` to discard the records in non-interactive mode."
)
RECOVER_DISCARD_DONE = "interrupted-update records discarded"
RECOVER_DISCARD_DRY_RUN = "interrupted-update records would be discarded"
RECOVER_NOT_AVAILABLE = "recover aborted — recovery is not available for this interrupted update."
RECOVER_CLEANUP_DRY_RUN = "completed update leftovers would be cleaned up"
RECOVER_CLEANUP_DONE = "completed update leftovers cleaned up"
RECOVER_DISCARD_CORRUPT_DONE = "discarded damaged interrupted-update record"
PUSH_JOURNAL_CREATE_FAILED = "push aborted — could not create the interrupted-update record."
PUSH_JOURNAL_CREATE_FAILED_LEFTOVER = (
    "push aborted — could not create the interrupted-update record; "
    "recovery snapshots may remain for manual review."
)
PUSH_JOURNAL_UPDATE_FAILED = "push aborted — could not update the interrupted-update record."
PUSH_JOURNAL_FINALIZE_FAILED = "push aborted — could not finish the interrupted-update record."
PUSH_WORDLIST_WRITE_FAILED = "push aborted — could not write the word list."
PUSH_WORDLIST_BACKUP_FAILED = "push aborted — could not back up the word list."
PUSH_DICTIONARY_BACKUPS_FAILED = "push aborted — could not back up any app dictionary."
PARTIAL_PULL_SKIPPED = "partial pull — some dictionaries were skipped."


def command_stopped_message(command: str) -> str:
    return f"{command} stopped."


def partial_push_skipped_message(skipped: tuple[str, ...] | list[str]) -> str:
    return f"partial push — skipped {len(skipped)} dictionary(s): {', '.join(skipped)}"


PULL_WORDLIST_WRITE_FAILED = "pull aborted — could not write the word list."
PULL_WORDLIST_CHANGED = "pull aborted — the word list changed since preview."
PULL_WORDLIST_APPEARED = "pull aborted — the word list appeared or changed since preview."
LINT_FIX_WRITE_FAILED = "lint --fix: could not write the word list."
LINT_WHITELIST_UNREADABLE = "lint allow-list is unreadable"
LOCK_PATH_UNSAFE = (
    "operation aborted — project lock path is unsafe. "
    "Inspect `.spell-sync.lock` in the project directory."
)


def config_blocks_mutation_message(status: str) -> str:
    return (
        f"operation aborted — invalid spell-sync.toml ({status}). "
        "Fix the config before Collect my words or Update my apps."
    )


RECOVER_DESCRIPTION = "Restore your word list and app dictionaries after an interrupted update."
RECOVER_ABORTED_CONFIRM = (
    "recover aborted — an interrupted update was found. "
    "Pass `--yes` to restore in non-interactive mode."
)
RECOVER_CONFIRM_PROMPT = (
    "Restore your word list and app dictionaries from recovery snapshots? [y/N] "
)
PUSH_TRANSACTION_START_FAILED = "push aborted — could not start the interrupted-update record."
RECOVER_DISCARD_HELP = "remove a damaged interrupted-update record without restoring (dangerous)"
RECOVERY_CLEANUP_TITLE = "Recovery cleanup completed"
RECOVERY_DISCARDED_TITLE = "Interrupted-update records discarded"
RECOVERY_DISCARDED_MESSAGE = "Interrupted-update records discarded."
RECOVERY_DISCARD_FAILED = "Discard could not remove interrupted-update records."
CLEANUP_PENDING_WARN = (
    "the update finished, but recovery files remain. Run `spell-sync recover` to clean them up."
)
DOCTOR_CORRUPT_JOURNAL = (
    "a damaged interrupted-update record was found. "
    "Run `spell-sync recover --discard-corrupt-journal` after inspection."
)
DOCTOR_UNSUPPORTED_JOURNAL = (
    "an interrupted-update record uses an unsupported format. "
    "Run `spell-sync recover --discard-corrupt-journal` after inspection."
)
DOCTOR_UNSAFE_JOURNAL = (
    "an unsafe interrupted-update file was found. "
    "Inspect `.spell-sync.journal.json` carefully before removing it."
)


def recover_cli_title(*, dry_run: bool) -> str:
    suffix = " (dry-run)" if dry_run else ""
    return f"recover{suffix}: restore an interrupted update"


def recover_found_detail(started_at: str, command: str, transaction_id: str) -> str:
    return f"interrupted update from {started_at} ({command}, {transaction_id})"


def mutation_aborted_unsafe_journal_message(detail: str) -> str:
    return (
        f"operation aborted — interrupted-update file is unsafe ({detail}). "
        "Inspect `.spell-sync.journal.json` carefully."
    )


def mutation_aborted_corrupt_journal_message(detail: str) -> str:
    return (
        f"operation aborted — interrupted-update record is damaged or unsupported "
        f"({detail}). Inspect `.spell-sync.journal.json` carefully."
    )


def recover_aborted_corrupt_journal_message(detail: str) -> str:
    return (
        "recover aborted — interrupted-update record is damaged or unsupported "
        f"({detail}). Pass `--discard-corrupt-journal` only if you intend "
        "to remove the damaged record without restoring."
    )


def doctor_unfinished_journal_message(started: str, pid: int) -> str:
    return (
        f"an interrupted update was found ({started}, pid {pid}). "
        "Run `spell-sync recover` before Collect my words or Update my apps."
    )


def mutation_aborted_journal_message(started: str, pid: int) -> str:
    return (
        f"operation aborted — an interrupted update was found "
        f"({started}, pid {pid}). "
        "Run `spell-sync recover` before changing files."
    )
