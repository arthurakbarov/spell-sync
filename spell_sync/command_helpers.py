"""Shared CLI helpers: wordlist resolution, output mode, JSON exits."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .application.mutation_scope import mutation_scope_for
from .application.project_resolution import resolve_project_wordlist
from .application.reports import PushPreview
from .application.requests import ProjectRef
from .cli_options import CliOptions
from .config import CONFIRM_YES, push_max_removals_without_confirm
from .exit_codes import ExitCode
from .json_output import (
    base_payload,
    emit_json,
    json_emitted,
    push_result_payload,
    reset_json_emission,
)
from .log import log
from .mutation_guards import (
    operation_lock_scope_for,
)
from .push_journal import (
    JournalLoadResult,
    JournalLoadStatus,
    journal_payload,
)
from .resolved_runtime import ResolvedRuntime
from .runtime_settings import RuntimeSettings
from .settings import config_blocks_mutating
from .sync_run import DictionaryDiff, PushResult, SyncRun  # noqa: F401


def invalid_config_exit_from_result(
    opts: CliOptions,
    command: str,
    result,
) -> int | None:
    """Block mutating commands when spell-sync.toml is invalid."""
    if not config_blocks_mutating(result):
        return None
    diagnostics = [
        {"path": item.path, "message": item.message, "kind": item.kind.value}
        for item in result.diagnostics
    ]
    if opts.json_output:
        emit_json(
            {
                **base_payload(command, exit=int(ExitCode.PUSH_ABORT)),
                "reason": "invalid_config",
                "config_status": result.status.value,
                "diagnostics": diagnostics,
            }
        )
    else:
        log.abort(
            "operation aborted — invalid spell-sync.toml "
            f"({result.status.value}). Fix config before mutating commands."
        )
    return int(ExitCode.PUSH_ABORT)


def run_from_scope(scope: ResolvedRuntime | int) -> SyncRun | int:
    if isinstance(scope, int):
        return scope
    return SyncRun(context=scope.context)


def push_skip_running_app_dicts(run: SyncRun) -> frozenset[str]:
    """
    Early push skip list for running-app dictionaries.

    Currently empty: running apps are handled via a late TOCTOU check immediately before each
    dictionary write (`running_app_skip_reasons` in sync_run). Keeping this hook empty avoids
    duplicate process checks and keeps skip reasons stable.
    """
    return frozenset()


@contextmanager
def operation_lock_scope(opts: CliOptions, command: str) -> Iterator[int | None]:
    """
    Acquire a project-wide lock for mutating commands.

    Yields None when the lock is held; yields an exit code when another live
    process already holds the lock.
    """
    from .cli_request_adapter import project_ref

    with operation_lock_scope_for(
        wordlist_path_for(project_ref(opts)),
        command,
        json_output=opts.json_output,
    ) as lock_exit:
        yield lock_exit


def unfinished_journal_exit_from_result(
    opts: CliOptions,
    command: str,
    result: JournalLoadResult,
    *,
    wordlist=None,
) -> int | None:
    """Return exit code when journal is in-progress or corrupt/unsupported."""
    if command == "recover":
        return None
    if result.status is JournalLoadStatus.ABSENT:
        return None
    if result.status is JournalLoadStatus.VALID_COMPLETED:
        return None
    if result.status in (
        JournalLoadStatus.CORRUPT,
        JournalLoadStatus.UNSUPPORTED_SCHEMA,
    ):
        reason = "corrupt_journal"
        detail = result.detail or result.status.value
        if opts.json_output:
            emit_json(
                {
                    **base_payload(command, exit=int(ExitCode.PUSH_ABORT)),
                    "reason": reason,
                    "detail": detail,
                }
            )
        else:
            wl = wordlist or wordlist_file_for(opts)
            log.abort(
                "operation aborted — push journal is corrupt or unsupported "
                f"({detail}). Inspect or remove "
                f"{wl.resolve().parent / '.spell-sync.journal.json'} carefully."
            )
        return int(ExitCode.PUSH_ABORT)
    journal = result.journal
    assert journal is not None
    if opts.json_output:
        emit_json(
            {
                **base_payload(command, exit=int(ExitCode.PUSH_ABORT)),
                "reason": "unfinished_transaction",
                "journal": journal_payload(journal),
            }
        )
    else:
        log.abort(
            "operation aborted — unfinished push journal found "
            f"({journal.started}, pid {journal.pid}). "
            "Run `spell-sync recover` before mutating commands."
        )
    return int(ExitCode.PUSH_ABORT)


def unfinished_journal_exit(opts: CliOptions, command: str) -> int | None:
    from .cli_request_adapter import project_ref
    from .push_journal import load_journal_result

    wordlist = wordlist_path_for(project_ref(opts))
    return unfinished_journal_exit_from_result(
        opts,
        command,
        load_journal_result(wordlist),
        wordlist=wordlist,
    )


@contextmanager
def mutating_command_scope(
    opts: CliOptions,
    command: str,
    *,
    allow_unfinished_journal: bool = False,
    strict_push_override: bool | None = None,
) -> Iterator[ResolvedRuntime | int]:
    from .cli_request_adapter import project_ref

    with mutating_command_scope_for(
        wordlist_path_for(project_ref(opts)),
        command,
        allow_unfinished_journal=allow_unfinished_journal,
        strict_push_override=strict_push_override,
        json_output=opts.json_output,
    ) as scope:
        yield scope


@contextmanager
def quiet_json_output(opts: CliOptions) -> Iterator[None]:
    was_quiet = log.quiet
    if opts.json_output:
        log.quiet = True
        reset_json_emission()
    try:
        yield
    finally:
        log.quiet = was_quiet


def emit_command_exit(
    opts: CliOptions,
    command: str,
    code: ExitCode,
    **extra: object,
) -> int:
    if opts.json_output:
        if json_emitted():
            return int(code)
        emit_json({**base_payload(command, exit=int(code)), **extra})
    return int(code)


def print_status_diff(diff: DictionaryDiff, *, verbose: bool) -> None:
    log.dictionary_status(
        diff.name,
        diff.target_count,
        diff.local_count,
        diff.to_add,
        diff.to_remove,
    )
    if verbose:
        log.dictionary_word_diff("add (push)", diff.add_words)
        log.dictionary_word_diff("remove (push)", diff.remove_words)


def dictionaries_label(count: int) -> str:
    if count == 0:
        return "0 dictionaries"
    word = "dictionary" if count == 1 else "dictionaries"
    return f"{count} {word}"


def format_push_done(result: PushResult) -> str:
    label = dictionaries_label(len(result.written))
    message = f"pushed {result.word_count} words to {label}"
    if result.skipped:
        if result.skipped_reasons:
            parts: list[str] = []
            for name in result.skipped:
                reason = result.skipped_reasons.get(name)
                detail = result.skipped_details.get(name)
                if reason and detail:
                    parts.append(f"{name} ({reason}: {detail})")
                elif reason:
                    parts.append(f"{name} ({reason})")
                else:
                    parts.append(name)
            message += f"; skipped: {', '.join(parts)}"
        else:
            message += f"; skipped: {', '.join(result.skipped)}"
    return message


def finish_push(
    result: PushResult | ExitCode,
    opts: CliOptions,
    *,
    dry_run: bool = False,
    command: str = "push",
    recovery_required: bool = False,
    outcome: str | None = None,
) -> int:
    if isinstance(result, ExitCode):
        extra: dict[str, object] = {"dry_run": dry_run}
        if recovery_required:
            extra["recovery_required"] = True
        if outcome is not None:
            extra["outcome"] = outcome
        return emit_command_exit(opts, command, result, **extra)

    exit_code = ExitCode.PARTIAL_PUSH if result.skipped else ExitCode.OK
    if opts.json_output:
        emit_json(
            {
                **base_payload(command, exit=int(exit_code)),
                "dry_run": dry_run,
                "partial": bool(result.skipped),
                **push_result_payload(result),
            }
        )
        return int(exit_code)

    message = format_push_done(result)
    prefix = "dry-run: " if dry_run else ""
    suffix = " (no writes performed)" if dry_run else ""
    log.done(f"{prefix}{message}{suffix}")
    if result.skipped:
        log.warn(
            f"partial push (exit {int(ExitCode.PARTIAL_PUSH)}) — "
            f"skipped {len(result.skipped)} dictionary(s): {', '.join(result.skipped)}"
        )
        log.detail("Re-run with `push --strict` to abort instead of partial success.")
    return int(exit_code)


def wordlist_path_for(project: ProjectRef):
    return resolve_project_wordlist(project)


def wordlist_file_for(opts: CliOptions):
    from .cli_request_adapter import project_ref

    return wordlist_path_for(project_ref(opts))


@contextmanager
def mutating_command_scope_for(
    wordlist: Path,
    command: str,
    *,
    allow_unfinished_journal: bool = False,
    strict_push_override: bool | None = None,
    json_output: bool = False,
) -> Iterator[ResolvedRuntime | int]:
    """Acquire lock, then load config and journal once for mutating commands."""
    with mutation_scope_for(
        wordlist,
        command,
        allow_unfinished_journal=allow_unfinished_journal,
        strict_push_override=strict_push_override,
        json_output=json_output,
    ) as scope:
        yield scope


def guard_exit_code(
    choice: bool | None,
    *,
    cancelled: ExitCode,
    quiet: bool = False,
) -> int | None:
    if choice is None:
        return int(ExitCode.SYNC_INTERRUPTED)
    if not choice:
        if not quiet:
            print("Cancelled.")
        return int(cancelled)
    return None


def confirm_push_removals_for_preview(
    preview: PushPreview,
    opts: CliOptions,
) -> bool | None:
    prepared = preview.prepared
    peak = prepared.max_removals() if prepared is not None else 0
    settings = prepared.ctx.settings if prepared is not None else RuntimeSettings.defaults()
    limit = push_max_removals_without_confirm(settings=settings)
    if peak <= limit or opts.yes or opts.dry_run:
        return True
    log.warn(
        f"push would remove up to {peak} words from a dictionary "
        f"(limit {limit} without confirmation)"
    )
    log.detail("Review `status --verbose`, or pass `--yes` to proceed.")
    interactive = sys.stdin.isatty() and not opts.json_output
    if not interactive:
        log.abort(
            "push aborted — too many removals without confirmation. "
            "Pass `--yes` to proceed in non-interactive mode."
        )
        return False
    try:
        answer = input("Continue push? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return None
    return answer in CONFIRM_YES


def confirm_push_removals(
    run: SyncRun,
    opts: CliOptions,
    *,
    peak_removals: int | None = None,
) -> bool | None:
    peak = peak_removals if peak_removals is not None else run.max_push_removals()
    limit = push_max_removals_without_confirm(settings=run.context.settings)
    if peak <= limit or opts.yes or opts.dry_run:
        return True
    log.warn(
        f"push would remove up to {peak} words from a dictionary "
        f"(limit {limit} without confirmation)"
    )
    log.detail("Review `status --verbose`, or pass `--yes` to proceed.")
    interactive = sys.stdin.isatty() and not opts.json_output
    if not interactive:
        log.abort(
            "push aborted — too many removals without confirmation. "
            "Pass `--yes` to proceed in non-interactive mode."
        )
        return False
    try:
        answer = input("Continue push? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return None
    return answer in CONFIRM_YES
