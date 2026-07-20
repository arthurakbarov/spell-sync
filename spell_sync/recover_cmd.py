"""Recover from an interrupted push using the on-disk journal."""

from __future__ import annotations

import sys

from .application import SpellSyncService
from .application.reports import RecoveryStatus
from .cli_options import CliOptions
from .cli_request_adapter import recovery_request
from .command_helpers import quiet_json_output
from .config import CONFIRM_YES
from .exit_codes import ExitCode
from .json_output import base_payload, emit_json
from .log import log
from .push_journal import RecoverResult

_SERVICE = SpellSyncService(enable_file_logging=False)


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
        dry_run = opts.dry_run
        mode = " (dry-run)" if dry_run else ""
        log.section(f"recover{mode}: restore from unfinished push journal")
        request = recovery_request(opts)
        preview = _SERVICE.inspect_recovery(request)

        if preview.status is RecoveryStatus.ABSENT:
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

        if preview.status is RecoveryStatus.COMPLETED_CLEANUP_PENDING:
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
                execution = _SERVICE.execute_recovery_cleanup(
                    request,
                    preview,
                    confirmed_transaction_id=preview.preview_fingerprint,
                )
                _SERVICE.build_recovery_report(execution)
            log.detail("recover: completed journal cleaned up")
            return int(ExitCode.OK)

        if preview.status in (RecoveryStatus.CORRUPT_JOURNAL, RecoveryStatus.UNSUPPORTED_SCHEMA):
            detail = preview.detail or preview.status.value
            if opts.discard_corrupt_journal and not dry_run:
                execution = _SERVICE.execute_recovery_discard(
                    request,
                    preview,
                    confirmed_transaction_id=preview.preview_fingerprint,
                )
                _SERVICE.build_recovery_report(execution)
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
            log.abort(
                "recover aborted — push journal is corrupt or unsupported "
                f"({detail}). Pass `--discard-corrupt-journal` only if you intend "
                "to remove the damaged journal without restoring."
            )
            return int(ExitCode.PUSH_ABORT)

        if not preview.can_recover:
            if opts.json_output:
                emit_json(
                    {
                        **base_payload("recover", exit=int(ExitCode.PUSH_ABORT)),
                        "reason": preview.status.value,
                        "detail": preview.detail,
                    }
                )
            log.abort("recover aborted — recovery is not available for this journal.")
            return int(ExitCode.PUSH_ABORT)

        if not dry_run and not opts.yes:
            interactive = sys.stdin.isatty() and not opts.json_output
            if not interactive:
                if opts.json_output:
                    emit_json(
                        {
                            **base_payload("recover", exit=int(ExitCode.PUSH_ABORT)),
                            "reason": "confirmation_required",
                            "journal": preview.journal_summary,
                        }
                    )
                    return int(ExitCode.PUSH_ABORT)
                log.abort(
                    "recover aborted — unfinished push journal found. "
                    "Pass `--yes` to restore from backups in non-interactive mode."
                )
                return int(ExitCode.PUSH_ABORT)
            log.warn(
                f"unfinished push journal from {preview.started_at} "
                f"({preview.command}, transaction {preview.transaction_id})"
            )
            try:
                answer = input(
                    "Restore wordlist and dictionaries from .bak backups? [y/N] "
                ).strip()
            except (EOFError, KeyboardInterrupt):
                print("\nCancelled.")
                return int(ExitCode.CANCELLED)
            if answer.lower() not in CONFIRM_YES:
                print("Cancelled.")
                return int(ExitCode.CANCELLED)

        execution = _SERVICE.execute_recovery(
            request,
            preview,
            confirmed_transaction_id=preview.preview_fingerprint,
            dry_run=dry_run,
        )
        if not dry_run:
            _SERVICE.build_recovery_report(execution)

        result = execution.result
        incomplete = isinstance(result, RecoverResult) and bool(result.failed or result.conflicts)
        exit_code = int(ExitCode.PUSH_ABORT if incomplete else ExitCode.OK)

        if opts.json_output:
            payload: dict[str, object] = {
                **base_payload("recover", exit=exit_code),
                "dry_run": dry_run,
                "restored": list(execution.restored),
                "skipped": list(execution.skipped),
                "failed": list(execution.failed),
                "conflicts": list(execution.conflicts),
            }
            if preview.transaction_state == "rollback_incomplete":
                payload["reason"] = "rollback_incomplete"
            if isinstance(result, RecoverResult):
                payload["journal"] = preview.journal_summary
            emit_json(payload)
            return exit_code

        if isinstance(result, RecoverResult):
            return _emit_recover_text(result, dry_run=dry_run)
        if isinstance(result, ExitCode):
            log.abort("recover aborted.")
            return int(result)
        return exit_code
