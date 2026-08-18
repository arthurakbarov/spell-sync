"""Shared CLI helpers: wordlist resolution, output mode, JSON exits."""

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .application.mutation_scope import mutation_scope_for
from .application.project_resolution import resolve_project_wordlist
from .cli_options import CliOptions
from .config import push_max_removals_without_confirm
from .exit_codes import ExitCode
from .guest_messages import command_stopped_message, partial_push_skipped_message
from .json_output import (
    base_payload,
    emit_json,
    json_emitted,
    push_result_payload,
    reset_json_emission,
)
from .keymap import is_confirmed
from .log import log
from .operation_presenter import OperationSession
from .operation_reports import PushPreview
from .resolved_runtime import ResolvedRuntime
from .runtime_settings import RuntimeSettings
from .sync_run import DictionaryDiff, PushResult


@contextmanager
def mutating_command_scope(
    opts: CliOptions,
    command: str,
    *,
    allow_unfinished_journal: bool = False,
    strict_push_override: bool | None = None,
) -> Iterator[ResolvedRuntime | int]:
    from .cli_request_adapter import project_ref

    with mutation_scope_for(
        resolve_project_wordlist(project_ref(opts)),
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
    session: OperationSession | None = None,
    warnings: tuple[str, ...] = (),
    wordlist: Path | None = None,
) -> int:
    if isinstance(result, ExitCode):
        extra: dict[str, object] = {"dry_run": dry_run}
        if recovery_required:
            extra["recovery_required"] = True
        if outcome is not None:
            extra["outcome"] = outcome
        if session is not None and not opts.json_output:
            message = command_stopped_message(command)
            if result in {ExitCode.CANCELLED, ExitCode.SYNC_INTERRUPTED}:
                session.abort(message)
            else:
                session.fail(message)
        return emit_command_exit(opts, command, result, **extra)

    exit_code = ExitCode.PARTIAL_PUSH if result.skipped else ExitCode.OK
    payload_warnings = list(warnings)
    for name in result.skipped:
        reason = result.skipped_reasons.get(name) or result.skipped_details.get(name) or "skipped"
        payload_warnings.append(f"Skipped {name}: {reason}")
    if opts.json_output:
        emit_json(
            {
                **base_payload(command, exit=int(exit_code)),
                "dry_run": dry_run,
                "partial": bool(result.skipped),
                "warnings": payload_warnings,
                **push_result_payload(result),
            }
        )
        return int(exit_code)

    message = format_push_done(result)
    prefix = "dry-run: " if dry_run else ""
    suffix = " (no writes performed)" if dry_run else ""
    done_line = f"{prefix}{message}{suffix}"
    for warning in warnings:
        log.warn(warning)
    if not dry_run:
        from .workspace_git import inspect_workspace_git, workspace_git_dirty_message

        root = wordlist.parent if wordlist is not None else wordlist_file_for(opts).parent
        git_status = inspect_workspace_git(root)
        if git_status is not None and git_status.is_dirty:
            dirty_message = workspace_git_dirty_message(git_status)
            if dirty_message not in warnings:
                log.warn(dirty_message)
    if session is not None:
        if result.skipped:
            session.warn_outcome(
                done_line,
                details=(
                    partial_push_skipped_message(result.skipped),
                    "Re-run with `push --strict` to abort instead of partial success.",
                ),
            )
        else:
            session.succeed(done_line)
        return int(exit_code)

    log.done(done_line)
    if result.skipped:
        log.warn(partial_push_skipped_message(result.skipped))
        log.detail("Re-run with `push --strict` to abort instead of partial success.")
    return int(exit_code)


def wordlist_file_for(opts: CliOptions):
    from .cli_request_adapter import project_ref

    return resolve_project_wordlist(project_ref(opts))


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
            log.write("Cancelled.")
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
        answer = input("Continue push? [y/N] ")
    except EOFError, KeyboardInterrupt:
        log.write("\nCancelled.")
        return None
    return is_confirmed(answer)
