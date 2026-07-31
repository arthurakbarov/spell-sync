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
    recovery_materials_preserved: bool = False


def _combined_reason(*parts: str) -> str:
    ordered = [part for part in parts if part]
    if not ordered:
        return "push_aborted"
    if len(ordered) == 1:
        return ordered[0]
    if "rollback_incomplete" in ordered and "journal_update_failed" in ordered:
        return "journal_update_failed"
    if "rollback_incomplete" in ordered:
        return "rollback_incomplete"
    return ordered[0]


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
    rollback_incomplete = rollback.failed

    if rollback_incomplete:
        journal_flag = "journal_update_failed" if journal_update_failed else ""
        json_reason = _combined_reason(reason, journal_flag, "rollback_incomplete")
        if journal_session is not None:
            try:
                journal_session.mark_rollback_incomplete()
            except OSError:
                pass
        suffix = "run `spell-sync recover`"
        if journal_update_failed:
            detail = f"journal update failed; rollback incomplete — {suffix}"
        else:
            detail = f"rollback incomplete — {suffix}"
        log.abort(f"{message} ({detail}).")
        return PushAbort(
            ExitCode.PUSH_ABORT,
            json_reason,
            message,
            recovery_materials_preserved=True,
        )

    if journal_update_failed:
        _best_effort_cleanup_after_complete_rollback(tx, journal_session)
        log.abort(message)
        return PushAbort(ExitCode.PUSH_ABORT, "journal_update_failed", message)

    _best_effort_cleanup_after_complete_rollback(tx, journal_session)
    log.abort(message)
    return PushAbort(ExitCode.PUSH_ABORT, reason, message)


def _best_effort_cleanup_after_complete_rollback(
    tx: PushTransaction,
    journal_session: PushJournalSession | None,
) -> None:
    if journal_session is not None:
        try:
            journal_session.discard()
        except OSError:
            pass
    tx.discard_snapshots()


def rollback_result_failed(result: RollbackResult) -> bool:
    return bool(result.failed)
