"""Controlled abort after partial push writes."""

from __future__ import annotations

from dataclasses import dataclass

from .exit_codes import ExitCode
from .log import log
from .push_journal import PushJournalSession
from .push_transaction import PushTransaction, RollbackResult


@dataclass(frozen=True)
class PushAbort:
    exit_code: ExitCode
    reason: str
    message: str


def handle_failed_push_rollback(
    tx: PushTransaction,
    journal_session: PushJournalSession | None,
    *,
    reason: str,
    message: str,
    journal_update_failed: bool = False,
) -> PushAbort:
    """Rollback after a failed push; preserve journal/snapshots when rollback is incomplete."""
    rollback = tx.rollback()
    json_reason = reason
    if journal_update_failed:
        json_reason = "journal_update_failed"
    elif rollback.failed:
        json_reason = "rollback_incomplete"
        if journal_session is not None:
            try:
                journal_session.mark_rollback_incomplete()
            except OSError:
                pass
        log.abort(f"{message} ({json_reason} — run `spell-sync recover`).")
        return PushAbort(ExitCode.PUSH_ABORT, json_reason, message)
    if journal_session is not None:
        try:
            journal_session.discard()
        except OSError:
            pass
    tx.discard_snapshots()
    log.abort(message)
    return PushAbort(ExitCode.PUSH_ABORT, json_reason, message)


def rollback_result_failed(result: RollbackResult) -> bool:
    return bool(result.failed)
