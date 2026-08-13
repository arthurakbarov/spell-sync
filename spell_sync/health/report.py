"""Build doctor/health reports from a SyncRun."""

from pathlib import Path

from ..app_process_check import (
    chrome_dictionaries_enabled,
    edge_dictionaries_enabled,
    firefox_dictionaries_enabled,
    is_chrome_running,
    is_edge_running,
    is_firefox_running,
    is_obsidian_running,
    obsidian_dictionaries_enabled,
)
from ..config import MACOS_APPLESPELL_FDA_HINT, TCC_ACCESS_HINT, enable_sublime
from ..dictionaries import Dictionary
from ..io import is_path_readable, is_path_writable
from ..paths import is_macos
from ..push_journal import JournalLoadStatus, load_journal_result
from ..runtime import cli_shell_prefix, installed_package_version
from ..settings import (
    config_blocks_mutating,
    load_config_result,
    load_project_settings_with_issues,
    unknown_config_keys,
)
from ..sublime_preferences import user_added_words_override_message
from ..workspace_git import inspect_workspace_git, workspace_git_dirty_message
from .actions import build_doctor_actions
from .inspect import git_hooks_checks, inspect_cli, inspect_git_hooks
from .types import DoctorCheck, DoctorReport


def _dictionary_writable(dictionary: Dictionary) -> bool:
    path = Path(dictionary.path)
    return is_path_writable(path)


def build_doctor_report(run) -> DoctorReport:
    checks: list[DoctorCheck] = []
    wordlist = Path(run.wordlist_str)

    settings, settings_issues = load_project_settings_with_issues(
        wordlist=wordlist,
    )
    config_result = load_config_result(wordlist=wordlist)
    # Match mutation_guards: blocking config must be doctor errors, not soft warns,
    # or `doctor --json` ok:true while every write aborts.
    config_level = "error" if config_blocks_mutating(config_result) else "warn"
    for issue in settings_issues:
        checks.append(DoctorCheck(config_level, f"config: {issue}"))
    for unknown in unknown_config_keys(settings):
        checks.append(DoctorCheck(config_level, f"config: {unknown}"))
    if (
        config_blocks_mutating(config_result)
        and not settings_issues
        and not unknown_config_keys(settings)
    ):
        for diagnostic in config_result.diagnostics:
            checks.append(DoctorCheck("error", f"config: {diagnostic.message}"))
        if not config_result.diagnostics:
            checks.append(
                DoctorCheck("error", f"config: {config_result.status.value}"),
            )

    if not wordlist.is_file():
        if wordlist.is_symlink():
            checks.append(
                DoctorCheck(
                    "error",
                    "wordlist.txt is a broken symlink. Fix the link or run init.",
                ),
            )
        else:
            checks.append(
                DoctorCheck("error", "wordlist.txt missing. Run init or create the file."),
            )
        word_count = 0
    else:
        unreadable = run.check_wordlist()
        if unreadable is not None:
            checks.append(
                DoctorCheck("error", f"wordlist unreadable {TCC_ACCESS_HINT}"),
            )
            word_count = 0
        else:
            words = run.load_wordlist()
            word_count = len(words)
            if word_count == 0:
                checks.append(
                    DoctorCheck(
                        "warn",
                        "wordlist is empty. push will abort until words are added.",
                    ),
                )
            risk = run.destructive_push_risk()
            if risk:
                checks.append(DoctorCheck("warn", risk))

    readable = 0
    writable = 0
    for dictionary in run.dictionaries:
        path = Path(dictionary.path)
        if is_path_readable(path):
            readable += 1
        if _dictionary_writable(dictionary):
            writable += 1

    skipped_unreadable = run.skipped_unreadable_dictionary_names()
    applespell_unreadable = any("applespell" in name.lower() for name in skipped_unreadable)
    for name in skipped_unreadable:
        if not (is_macos() and "applespell" in name.lower()):
            checks.append(
                DoctorCheck(
                    "warn",
                    f"{name}: read failed (path permissions) {TCC_ACCESS_HINT}",
                ),
            )

    if is_macos() and applespell_unreadable:
        checks.append(DoctorCheck("warn", MACOS_APPLESPELL_FDA_HINT))
    elif is_macos() and readable < len(run.dictionaries):
        checks.append(
            DoctorCheck(
                "info",
                "macOS: grant Full Disk Access to your terminal app "
                "if dictionaries stay unreadable.",
            ),
        )

    settings = run.context.settings

    def _warn_running(app: str, detail: str, probe) -> None:
        state = probe()
        if state is True:
            checks.append(DoctorCheck("warn", detail))
        elif state is None:
            checks.append(
                DoctorCheck(
                    "warn",
                    f"Could not verify whether {app} is quit. "
                    "Quit the app before push, or re-check Health.",
                ),
            )

    if chrome_dictionaries_enabled(settings=settings):
        _warn_running(
            "Chrome",
            "Chrome is running. Quit Chrome before push so Custom Dictionary.txt is not locked.",
            is_chrome_running,
        )

    if edge_dictionaries_enabled(settings=settings):
        _warn_running(
            "Edge",
            "Edge is running. Quit Edge before push so Custom Dictionary.txt is not locked.",
            is_edge_running,
        )

    if firefox_dictionaries_enabled(settings=settings):
        _warn_running(
            "Firefox",
            "Firefox is running. Quit Firefox before push so persdict.dat is not locked.",
            is_firefox_running,
        )

    if obsidian_dictionaries_enabled(settings=settings):
        _warn_running(
            "Obsidian",
            "Obsidian is running. Quit Obsidian before push "
            "so Custom Dictionary.txt is not locked.",
            is_obsidian_running,
        )

    if enable_sublime(settings=settings):
        override = user_added_words_override_message()
        if override is not None:
            checks.append(DoctorCheck("warn", override))

    git_status = inspect_workspace_git(wordlist.parent if wordlist.is_file() else wordlist)
    if git_status is not None and git_status.is_dirty:
        checks.append(DoctorCheck("warn", workspace_git_dirty_message(git_status)))

    if readable and writable < readable:
        checks.append(
            DoctorCheck(
                "warn",
                f"{writable}/{readable} readable dictionaries are writable. "
                "Check permissions before push.",
            ),
        )

    diffs = run.status_diffs(quiet_unreadable=True) if word_count else []
    max_add = max((d.to_add for d in diffs), default=0)
    max_remove = max((d.to_remove for d in diffs), default=0)

    from ..workspace_git import resolve_git_hooks_dir

    hooks_dir = resolve_git_hooks_dir(wordlist.parent if wordlist.is_file() else wordlist)
    git_hooks = inspect_git_hooks(hooks_dir) if hooks_dir is not None else None
    if git_hooks is not None:
        checks.extend(git_hooks_checks(git_hooks))

    cli_status = inspect_cli()
    if not cli_status.on_path:
        if cli_status.path_export:
            checks.append(
                DoctorCheck(
                    "info",
                    f"spell-sync not on PATH — add: {cli_status.path_export} "
                    f"(or use: {cli_shell_prefix()} …)",
                ),
            )
        else:
            checks.append(
                DoctorCheck(
                    "info",
                    f"spell-sync not on PATH — use: {cli_shell_prefix()} … "
                    "(git hooks use the same fallback)",
                ),
            )

    journal_result = load_journal_result(wordlist)
    unfinished_journal = (
        journal_result.journal
        if journal_result.status is JournalLoadStatus.VALID_IN_PROGRESS
        else None
    )
    if unfinished_journal is not None:
        checks.append(
            DoctorCheck(
                "error",
                "unfinished push journal found "
                f"({unfinished_journal.started}, pid {unfinished_journal.pid}). "
                "Run `spell-sync recover` before pull or push.",
            ),
        )
    elif journal_result.status is JournalLoadStatus.CORRUPT:
        checks.append(
            DoctorCheck(
                "error",
                "corrupt push journal found. "
                "Run `spell-sync recover --discard-corrupt-journal` after inspection.",
            ),
        )
    elif journal_result.status is JournalLoadStatus.UNSUPPORTED_SCHEMA:
        checks.append(
            DoctorCheck(
                "error",
                "unsupported push journal schema. "
                "Run `spell-sync recover --discard-corrupt-journal` after inspection.",
            ),
        )
    elif journal_result.status is JournalLoadStatus.UNSAFE_ARTIFACT:
        checks.append(
            DoctorCheck(
                "error",
                "unsafe push journal artifact found. "
                "Inspect `.spell-sync.journal.json` carefully before removing it.",
            ),
        )

    applicable = run.dictionaries
    actions = build_doctor_actions(
        skipped_unreadable=skipped_unreadable,
        git_hooks=git_hooks,
        cli_status=cli_status,
        unfinished_journal=unfinished_journal is not None
        or journal_result.status
        in {
            JournalLoadStatus.CORRUPT,
            JournalLoadStatus.UNSUPPORTED_SCHEMA,
            JournalLoadStatus.UNSAFE_ARTIFACT,
        },
    )
    return DoctorReport(
        wordlist_path=str(wordlist),
        wordlist_count=word_count,
        package_version=installed_package_version(),
        skipped_unreadable=skipped_unreadable,
        git_hooks=git_hooks,
        cli=cli_status,
        actions=actions,
        checks=tuple(checks),
        dictionaries_total=len(applicable),
        dictionaries_readable=readable,
        dictionaries_writable=writable,
        max_drift_add=max_add,
        max_drift_remove=max_remove,
    )
