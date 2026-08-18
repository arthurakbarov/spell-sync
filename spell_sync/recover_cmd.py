"""Recover from an interrupted update."""

import sys
from typing import Any

from .application import SpellSyncService
from .application.requests import RecoveryRequest
from .cli_options import CliOptions
from .cli_request_adapter import recovery_request
from .command_helpers import quiet_json_output
from .exit_codes import ExitCode
from .guest_messages import (
    RECOVER_ABORTED_CONFIRM,
    RECOVER_CLEANUP_DONE,
    RECOVER_CLEANUP_DRY_RUN,
    RECOVER_CONFIRM_PROMPT,
    RECOVER_DESCRIPTION,
    RECOVER_DISCARD_ABORTED,
    RECOVER_DISCARD_CORRUPT_DONE,
    RECOVER_DISCARD_DONE,
    RECOVER_DISCARD_DRY_RUN,
    RECOVER_DISCARD_PROMPT,
    RECOVER_DRY_RUN_NOTHING,
    RECOVER_NONE_FOUND,
    RECOVER_NOT_AVAILABLE,
    RECOVER_NOTHING_TO_RESTORE,
    recover_aborted_corrupt_journal_message,
    recover_cli_title,
    recover_found_detail,
)
from .json_output import base_payload, emit_json
from .keymap import is_confirmed
from .log import log
from .operation_presenter import OperationSession, OperationSpec, operation_session
from .operation_reports import (
    RecoveryExecution,
    RecoveryOutcome,
    RecoveryPreview,
    RecoveryStatus,
)
from .push_journal import RecoverResult

_SERVICE = SpellSyncService(enable_file_logging=False)


def _history_duration_ms(session: OperationSession | None) -> int:
    return session.elapsed_ms if session is not None else 0


def _emit_recover_text(
    result: RecoverResult,
    *,
    dry_run: bool,
    session: OperationSession | None,
) -> int:
    if result.failed or result.conflicts:
        parts = []
        if result.failed:
            parts.append(f"failed: {', '.join(result.failed)}")
        if result.conflicts:
            parts.append(f"conflicts: {', '.join(result.conflicts)}")
        message = f"recover incomplete — {'; '.join(parts)}"
        if session is not None:
            session.abort(message)
        else:
            log.abort(message)
        return int(ExitCode.PUSH_ABORT)
    if dry_run:
        if result.restored:
            message = f"recover dry-run would restore: {', '.join(result.restored)}"
            if session is not None:
                session.succeed(message)
            else:
                log.done(message)
        elif session is not None:
            session.succeed(RECOVER_DRY_RUN_NOTHING)
        else:
            log.detail(RECOVER_DRY_RUN_NOTHING)
    elif result.restored:
        message = f"recover restored: {', '.join(result.restored)}"
        if session is not None:
            session.succeed(message)
        else:
            log.done(message)
    elif session is not None:
        session.succeed(RECOVER_NOTHING_TO_RESTORE)
    else:
        log.detail(f"recover: {RECOVER_NOTHING_TO_RESTORE}")
    return int(ExitCode.OK)


def _exit_from_recovery_execution(execution: RecoveryExecution) -> int:
    result = execution.result
    outcome = execution.outcome
    if isinstance(result, ExitCode):
        return int(result)
    if isinstance(result, RecoverResult):
        if result.failed or result.conflicts:
            return int(ExitCode.PUSH_ABORT)
        return int(ExitCode.OK)
    if outcome in (
        RecoveryOutcome.RECOVERED,
        RecoveryOutcome.RECOVERED_WITH_WARNINGS,
        RecoveryOutcome.CLEANUP_COMPLETED,
        RecoveryOutcome.DISCARDED,
    ):
        return int(ExitCode.OK)
    return int(ExitCode.PUSH_ABORT)


def _require_recover_confirmation(
    opts: CliOptions,
    *,
    preview: RecoveryPreview,
    session: OperationSession | None,
    abort_message: str,
    prompt: str,
) -> int | None:
    if opts.yes:
        return None
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
        if session is not None:
            session.abort(abort_message)
        else:
            log.abort(abort_message)
        return int(ExitCode.PUSH_ABORT)
    log.warn(recover_found_detail(preview.started_at, preview.command, preview.transaction_id))
    try:
        answer = input(prompt)
    except EOFError, KeyboardInterrupt:
        log.write("\nCancelled.")
        return int(ExitCode.CANCELLED)
    if not is_confirmed(answer):
        log.write("Cancelled.")
        return int(ExitCode.CANCELLED)
    return None


def _cmd_recover_discard_records(
    opts: CliOptions,
    request: RecoveryRequest,
    preview: RecoveryPreview,
    *,
    dry_run: bool,
    session: OperationSession | None,
) -> int:
    if dry_run:
        if opts.json_output:
            emit_json(
                {
                    **base_payload("recover", exit=int(ExitCode.OK)),
                    "dry_run": True,
                    "action": "discard",
                    "restored": [],
                    "skipped": [],
                    "failed": [],
                }
            )
        if session is not None:
            session.succeed(RECOVER_DISCARD_DRY_RUN)
        else:
            log.detail(f"recover: {RECOVER_DISCARD_DRY_RUN}")
        return int(ExitCode.OK)
    denied = _require_recover_confirmation(
        opts,
        preview=preview,
        session=session,
        abort_message=RECOVER_DISCARD_ABORTED,
        prompt=RECOVER_DISCARD_PROMPT,
    )
    if denied is not None:
        return denied
    execution = _SERVICE.execute_recovery_discard(
        request,
        preview,
        confirmed_transaction_id=preview.preview_fingerprint,
        event_sink=session,
    )
    _SERVICE.build_recovery_report(execution, duration_ms=_history_duration_ms(session))
    exit_code = _exit_from_recovery_execution(execution)
    if opts.json_output:
        emit_json(
            {
                **base_payload("recover", exit=exit_code),
                "dry_run": False,
                "action": "discard",
                "outcome": execution.outcome.value,
            }
        )
    if exit_code == int(ExitCode.OK):
        if session is not None:
            session.succeed(RECOVER_DISCARD_DONE)
        else:
            log.detail(f"recover: {RECOVER_DISCARD_DONE}")
    elif session is not None:
        session.abort(execution.message or "recover discard failed.")
    else:
        log.abort(execution.message or "recover discard failed.")
    return exit_code


def cmd_recover(opts: CliOptions) -> int:
    with quiet_json_output(opts):
        dry_run = opts.dry_run
        with operation_session(
            OperationSpec(
                key="recover",
                title=recover_cli_title(dry_run=dry_run),
                descriptions=(RECOVER_DESCRIPTION,),
                activity="Recovery",
            ),
            enabled=not opts.json_output,
        ) as session:
            return _cmd_recover_body(opts, dry_run=dry_run, session=session)


def _cmd_recover_body(
    opts: CliOptions,
    *,
    dry_run: bool,
    session: OperationSession | None,
) -> int:
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
        if session is not None:
            session.succeed(RECOVER_NONE_FOUND)
        else:
            log.detail(f"recover: {RECOVER_NONE_FOUND}")
        return int(ExitCode.OK)

    if preview.status is RecoveryStatus.COMPLETED_CLEANUP_PENDING:
        if dry_run:
            if opts.json_output:
                emit_json(
                    {
                        **base_payload("recover", exit=int(ExitCode.OK)),
                        "dry_run": True,
                        "action": "cleanup",
                        "restored": [],
                        "skipped": [],
                        "failed": [],
                    }
                )
            if session is not None:
                session.succeed(RECOVER_CLEANUP_DRY_RUN)
            else:
                log.detail(f"recover: {RECOVER_CLEANUP_DRY_RUN}")
            return int(ExitCode.OK)
        execution = _SERVICE.execute_recovery_cleanup(
            request,
            preview,
            confirmed_transaction_id=preview.preview_fingerprint,
            event_sink=session,
        )
        _SERVICE.build_recovery_report(execution, duration_ms=_history_duration_ms(session))
        exit_code = _exit_from_recovery_execution(execution)
        if opts.json_output:
            emit_json(
                {
                    **base_payload("recover", exit=exit_code),
                    "dry_run": False,
                    "action": "cleanup",
                    "restored": [],
                    "skipped": [],
                    "failed": [],
                    "outcome": execution.outcome.value,
                }
            )
        if exit_code == int(ExitCode.OK):
            if session is not None:
                session.succeed(RECOVER_CLEANUP_DONE)
            else:
                log.detail(f"recover: {RECOVER_CLEANUP_DONE}")
        elif session is not None:
            session.abort(execution.message or "recover cleanup failed.")
        else:
            log.abort(execution.message or "recover cleanup failed.")
        return exit_code

    if preview.status in (RecoveryStatus.CORRUPT_JOURNAL, RecoveryStatus.UNSUPPORTED_SCHEMA):
        detail = preview.detail or preview.status.value
        if opts.discard_corrupt_journal and not dry_run:
            execution = _SERVICE.execute_recovery_discard(
                request,
                preview,
                confirmed_transaction_id=preview.preview_fingerprint,
                event_sink=session,
            )
            _SERVICE.build_recovery_report(execution, duration_ms=_history_duration_ms(session))
            exit_code = _exit_from_recovery_execution(execution)
            if opts.json_output:
                emit_json(
                    {
                        **base_payload("recover", exit=exit_code),
                        "dry_run": dry_run,
                        "action": "discarded_corrupt_journal",
                        "detail": detail,
                        "outcome": execution.outcome.value,
                    }
                )
            if exit_code == int(ExitCode.OK):
                if session is not None:
                    session.warn_outcome(f"{RECOVER_DISCARD_CORRUPT_DONE} ({detail})")
                else:
                    log.warn(f"recover: {RECOVER_DISCARD_CORRUPT_DONE} ({detail})")
            elif session is not None:
                session.abort(execution.message or "recover discard failed.")
            else:
                log.abort(execution.message or "recover discard failed.")
            return exit_code
        if opts.json_output:
            emit_json(
                {
                    **base_payload("recover", exit=int(ExitCode.PUSH_ABORT)),
                    "reason": "corrupt_journal",
                    "detail": detail,
                }
            )
        message = recover_aborted_corrupt_journal_message(detail)
        if session is not None:
            session.abort(message)
        else:
            log.abort(message)
        return int(ExitCode.PUSH_ABORT)

    if preview.can_discard and not preview.can_recover and not preview.can_cleanup:
        return _cmd_recover_discard_records(
            opts, request, preview, dry_run=dry_run, session=session
        )

    if not preview.can_recover:
        if opts.json_output:
            emit_json(
                {
                    **base_payload("recover", exit=int(ExitCode.PUSH_ABORT)),
                    "reason": preview.status.value,
                    "detail": preview.detail,
                }
            )
        if session is not None:
            session.abort(RECOVER_NOT_AVAILABLE)
        else:
            log.abort(RECOVER_NOT_AVAILABLE)
        return int(ExitCode.PUSH_ABORT)

    if not dry_run:
        denied = _require_recover_confirmation(
            opts,
            preview=preview,
            session=session,
            abort_message=RECOVER_ABORTED_CONFIRM,
            prompt=RECOVER_CONFIRM_PROMPT,
        )
        if denied is not None:
            return denied

    execution = _SERVICE.execute_recovery(
        request,
        preview,
        confirmed_transaction_id=preview.preview_fingerprint,
        dry_run=dry_run,
        event_sink=session,
    )
    if not dry_run:
        _SERVICE.build_recovery_report(execution, duration_ms=_history_duration_ms(session))

    result: Any = execution.result
    exit_code = _exit_from_recovery_execution(execution)

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
        return _emit_recover_text(result, dry_run=dry_run, session=session)
    if isinstance(result, ExitCode):
        if session is not None:
            session.abort(execution.message or "recover aborted.")
        else:
            log.abort(execution.message or "recover aborted.")
        return int(result)
    return exit_code
