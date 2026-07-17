"""Recover from an interrupted push using the on-disk journal."""

from __future__ import annotations

import sys

from .cli_options import CliOptions
from .command_helpers import (
    mutating_command_scope,
    quiet_json_output,
    wordlist_file_for,
)
from .config import CONFIRM_YES
from .exit_codes import ExitCode
from .json_output import base_payload, emit_json
from .log import log
from .push_journal import (
    JournalLoadStatus,
    RecoverResult,
    cleanup_after_successful_recovery,
    discard_journal,
    journal_payload,
    recover_from_journal,
)


def _emit_recover_text(result: RecoverResult, *, dry_run: bool) -> int:
    if result.failed or result.conflicts:
        parts = []
        if result.failed:
            parts.append(f"failed: {', '.join(result.failed)}")
        if result.conflicts:
            parts.append(f"conflicts: {', '.join(result.conflicts)}")
        log.abort(f"recover incomplete — {'; '.join(parts)}")
        return int(ExitCode.PUSH_ABORT)
    if dry_run:
        if result.restored:
            log.done(f"recover dry-run would restore: {', '.join(result.restored)}")
        else:
            log.detail("recover dry-run: nothing to restore from journal backups")
    elif result.restored:
        log.done(f"recover restored: {', '.join(result.restored)}")
    else:
        log.detail("recover: nothing to restore from journal backups")
    return int(ExitCode.OK)


def cmd_recover(opts: CliOptions) -> int:
    with quiet_json_output(opts):
        with mutating_command_scope(
            opts,
            "recover",
            allow_unfinished_journal=True,
        ) as scope:
            if isinstance(scope, int):
                return scope
            return _cmd_recover_locked(opts, validated=scope)


def _cmd_recover_locked(opts: CliOptions, *, validated=None) -> int:
    dry_run = opts.dry_run
    mode = " (dry-run)" if dry_run else ""
    log.section(f"recover{mode}: restore from unfinished push journal")
    wordlist = wordlist_file_for(opts)
    load_result = validated.journal_result if validated is not None else None
    if load_result is None:
        from .push_journal import load_journal_result

        load_result = load_journal_result(wordlist, validate_wordlist=True)

    if load_result.status is JournalLoadStatus.ABSENT:
        if opts.json_output:
            emit_json(
                {
                    **base_payload("recover", exit=int(ExitCode.OK)),
                    "dry_run": dry_run,
                    "action": "none",
                    "restored": [],
                    "skipped": [],
                    "failed": [],
                }
            )
        log.detail("recover: no unfinished push journal found")
        return int(ExitCode.OK)

    if load_result.status is JournalLoadStatus.VALID_COMPLETED:
        if opts.json_output:
            emit_json(
                {
                    **base_payload("recover", exit=int(ExitCode.OK)),
                    "dry_run": dry_run,
                    "action": "cleanup",
                    "restored": [],
                    "skipped": [],
                    "failed": [],
                }
            )
        if not dry_run:
            discard_journal(wordlist)
        log.detail("recover: completed journal cleaned up")
        return int(ExitCode.OK)

    if load_result.status in (
        JournalLoadStatus.CORRUPT,
        JournalLoadStatus.UNSUPPORTED_SCHEMA,
    ):
        detail = load_result.detail or load_result.status.value
        if opts.discard_corrupt_journal and not dry_run:
            discard_journal(wordlist)
            if opts.json_output:
                emit_json(
                    {
                        **base_payload("recover", exit=int(ExitCode.OK)),
                        "dry_run": dry_run,
                        "action": "discarded_corrupt_journal",
                        "detail": detail,
                    }
                )
            log.warn(f"recover: discarded corrupt journal ({detail})")
            return int(ExitCode.OK)
        if opts.json_output:
            emit_json(
                {
                    **base_payload("recover", exit=int(ExitCode.PUSH_ABORT)),
                    "reason": "corrupt_journal",
                    "detail": detail,
                }
            )
        else:
            log.abort(
                "recover aborted — push journal is corrupt or unsupported "
                f"({detail}). Pass `--discard-corrupt-journal` only if you intend "
                "to remove the damaged journal without restoring."
            )
        return int(ExitCode.PUSH_ABORT)

    journal = load_result.journal
    assert journal is not None

    if not dry_run and not opts.yes:
        interactive = sys.stdin.isatty() and not opts.json_output
        if not interactive:
            if opts.json_output:
                emit_json(
                    {
                        **base_payload("recover", exit=int(ExitCode.PUSH_ABORT)),
                        "reason": "confirmation_required",
                        "journal": journal_payload(journal),
                    }
                )
                return int(ExitCode.PUSH_ABORT)
            log.abort(
                "recover aborted — unfinished push journal found. "
                "Pass `--yes` to restore from backups in non-interactive mode."
            )
            return int(ExitCode.PUSH_ABORT)
        log.warn(
            f"unfinished push journal from {journal.started} ({journal.command}, pid {journal.pid})"
        )
        try:
            answer = input("Restore wordlist and dictionaries from .bak backups? [y/N] ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return int(ExitCode.CANCELLED)
        if answer.lower() not in CONFIRM_YES:
            print("Cancelled.")
            return int(ExitCode.CANCELLED)

    result = recover_from_journal(journal, dry_run=dry_run)
    incomplete = bool(result.failed or result.conflicts)
    exit_code = int(ExitCode.PUSH_ABORT if incomplete else ExitCode.OK)
    if not dry_run and not incomplete:
        cleanup_after_successful_recovery(journal)

    if opts.json_output:
        payload: dict[str, object] = {
            **base_payload("recover", exit=exit_code),
            "dry_run": dry_run,
            "journal": journal_payload(journal),
            "restored": list(result.restored),
            "skipped": list(result.skipped),
            "failed": list(result.failed),
            "conflicts": list(result.conflicts),
        }
        if journal.state == "rollback_incomplete":
            payload["reason"] = "rollback_incomplete"
        emit_json(payload)
        return exit_code
    return _emit_recover_text(result, dry_run=dry_run)
