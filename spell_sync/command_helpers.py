"""Shared CLI helpers: wordlist resolution, output mode, JSON exits."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from .cli_options import CliOptions
from .config import CONFIRM_YES, push_max_removals_without_confirm
from .exit_codes import ExitCode
from .json_output import base_payload, emit_json, push_result_payload
from .log import log
from .operation_lock import OperationLocked, acquire_operation_lock, lock_info_payload
from .paths import resolve_wordlist_path
from .push_journal import (
    JournalLoadResult,
    JournalLoadStatus,
    journal_payload,
)
from .settings import config_blocks_mutating
from .sync_run import DictionaryDiff, PushResult, SyncRun, sync_run_for  # noqa: F401
from .validated_runtime import ValidatedRuntime, build_validated_runtime

_active_validated: ContextVar[ValidatedRuntime | None] = ContextVar(
    "_active_validated",
    default=None,
)


def active_validated_runtime() -> ValidatedRuntime | None:
    return _active_validated.get()


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


def invalid_config_exit(opts: CliOptions, command: str) -> int | None:
    """Pre-lock config check; prefer ``mutating_command_scope`` for mutating commands."""
    from .validated_runtime import build_validated_runtime

    wordlist = wordlist_file_for(opts)
    validated = build_validated_runtime(wordlist)
    return invalid_config_exit_from_result(opts, command, validated.config_result)


def run_from_scope(scope: ValidatedRuntime | int) -> SyncRun | int:
    if isinstance(scope, int):
        return scope
    return SyncRun(context=scope.context)


def push_skip_running_app_dicts(run: SyncRun, opts: CliOptions) -> frozenset[str]:
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
    wordlist = wordlist_file_for(opts)
    try:
        with acquire_operation_lock(wordlist, command):
            yield None
    except OperationLocked as exc:
        if opts.json_output:
            emit_json(
                {
                    **base_payload(command, exit=int(ExitCode.PUSH_ABORT)),
                    "reason": "operation_locked",
                    "lock": lock_info_payload(exc.info),
                }
            )
        else:
            log.abort(
                "operation aborted — another spell-sync process is running "
                f"({exc.info.command}, pid {exc.info.pid}). "
                f"Lock file: {exc.lock_path}"
            )
        yield int(ExitCode.PUSH_ABORT)


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
    wordlist = wordlist_file_for(opts)
    from .push_journal import load_journal_result

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
    strict_push: bool = False,
) -> Iterator[ValidatedRuntime | int]:
    """Acquire lock, then load config and journal once for mutating commands."""
    wordlist = wordlist_file_for(opts)
    with operation_lock_scope(opts, command) as lock_exit:
        if lock_exit is not None:
            yield lock_exit
            return
        validated = build_validated_runtime(wordlist, strict_push=strict_push)
        config_exit = invalid_config_exit_from_result(opts, command, validated.config_result)
        if config_exit is not None:
            yield config_exit
            return
        journal_exit = None
        if not allow_unfinished_journal:
            journal_exit = unfinished_journal_exit_from_result(
                opts,
                command,
                validated.journal_result,
                wordlist=wordlist,
            )
        if journal_exit is not None:
            yield journal_exit
            return
        token = _active_validated.set(validated)
        try:
            yield validated
        finally:
            _active_validated.reset(token)


@contextmanager
def quiet_json_output(opts: CliOptions) -> Iterator[None]:
    was_quiet = log.quiet
    if opts.json_output:
        log.quiet = True
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
) -> int:
    if isinstance(result, ExitCode):
        return emit_command_exit(opts, command, result, dry_run=dry_run)

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


def wordlist_file_for(opts: CliOptions):
    return resolve_wordlist_path(opts.wordlist)


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


def confirm_push_removals(
    run: SyncRun,
    opts: CliOptions,
    *,
    peak_removals: int | None = None,
) -> bool | None:
    peak = peak_removals if peak_removals is not None else run.max_push_removals()
    limit = push_max_removals_without_confirm()
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
