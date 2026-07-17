"""Build doctor/health reports from a SyncRun."""

from __future__ import annotations

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
from ..config import MACOS_APPLESPELL_FDA_HINT, TCC_ACCESS_HINT
from ..dictionaries import Dictionary
from ..io import is_path_readable, is_path_writable
from ..paths import is_macos
from ..push_journal import load_push_journal
from ..runtime import cli_shell_prefix, installed_package_version
from ..settings import load_user_settings_with_issues, unknown_config_keys
from .actions import build_doctor_actions
from .inspect import git_hooks_checks, inspect_cli, inspect_git_hooks
from .types import DoctorCheck, DoctorReport


def _dictionary_writable(dictionary: Dictionary) -> bool:
    path = Path(dictionary.path)
    return is_path_writable(path)


def build_doctor_report(run) -> DoctorReport:
    checks: list[DoctorCheck] = []
    wordlist = Path(run.wordlist_str)

    settings, settings_issues = load_user_settings_with_issues(
        wordlist=wordlist,
        reload=True,
    )
    for issue in settings_issues:
        checks.append(DoctorCheck("warn", f"config: {issue}"))
    for unknown in unknown_config_keys(settings):
        checks.append(DoctorCheck("warn", f"config: {unknown}"))

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

    if chrome_dictionaries_enabled() and is_chrome_running() is True:
        checks.append(
            DoctorCheck(
                "warn",
                "Chrome is running. Quit Chrome before push "
                "so Custom Dictionary.txt is not locked.",
            ),
        )

    if edge_dictionaries_enabled() and is_edge_running() is True:
        checks.append(
            DoctorCheck(
                "warn",
                "Edge is running. Quit Edge before push so Custom Dictionary.txt is not locked.",
            ),
        )

    if firefox_dictionaries_enabled() and is_firefox_running() is True:
        checks.append(
            DoctorCheck(
                "warn",
                "Firefox is running. Quit Firefox before push so persdict.dat is not locked.",
            ),
        )

    if obsidian_dictionaries_enabled() and is_obsidian_running() is True:
        checks.append(
            DoctorCheck(
                "warn",
                "Obsidian is running. Quit Obsidian before push "
                "so Custom Dictionary.txt is not locked.",
            ),
        )

    diffs = run.status_diffs(quiet_unreadable=True) if word_count else []
    max_add = max((d.to_add for d in diffs), default=0)
    max_remove = max((d.to_remove for d in diffs), default=0)

    hooks_dir = run.context.project_dir / ".git" / "hooks"
    git_hooks = inspect_git_hooks(hooks_dir)
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

    unfinished_journal = load_push_journal(wordlist)
    if unfinished_journal is not None:
        checks.append(
            DoctorCheck(
                "error",
                "unfinished push journal found "
                f"({unfinished_journal.started}, pid {unfinished_journal.pid}). "
                "Run `spell-sync recover` before pull or push.",
            ),
        )

    applicable = run.dictionaries
    actions = build_doctor_actions(
        skipped_unreadable=skipped_unreadable,
        git_hooks=git_hooks,
        cli_status=cli_status,
        unfinished_journal=unfinished_journal is not None,
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
