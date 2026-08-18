"""Build the UI-neutral recovery preview snapshot."""

from ..push_journal import (
    JOURNAL_STATE_ROLLBACK_INCOMPLETE,
    JournalLoadStatus,
    journal_payload,
    plan_recovery_from_journal,
)
from ..resolved_runtime import ResolvedRuntime
from .product_concepts import (
    RECOVERY_CLEANUP_REMAINING,
    RECOVERY_INERT_DETAIL,
    RECOVERY_INERT_WARNING,
    RECOVERY_NONE_FOUND,
)
from .reports import RecoveryItemPreview, RecoveryPreview, RecoveryStatus


def build_recovery_preview(validated: ResolvedRuntime) -> RecoveryPreview:
    wordlist_path = str(validated.context.wordlist_file)
    journal_result = validated.journal_result
    status = journal_result.status

    if status is JournalLoadStatus.ABSENT:
        return RecoveryPreview.unavailable(
            status=RecoveryStatus.ABSENT,
            wordlist_path=wordlist_path,
            detail=RECOVERY_NONE_FOUND,
        )
    if status is JournalLoadStatus.CORRUPT:
        return RecoveryPreview.unavailable(
            status=RecoveryStatus.CORRUPT_JOURNAL,
            wordlist_path=wordlist_path,
            detail=journal_result.detail or status.value,
            can_discard=True,
            preview_fingerprint=journal_result.content_digest or "corrupt",
        )
    if status is JournalLoadStatus.UNSAFE_ARTIFACT:
        return RecoveryPreview.unavailable(
            status=RecoveryStatus.CORRUPT_JOURNAL,
            wordlist_path=wordlist_path,
            detail=journal_result.detail or status.value,
            can_discard=False,
            preview_fingerprint=journal_result.content_digest or "unsafe",
        )
    if status is JournalLoadStatus.UNSUPPORTED_SCHEMA:
        return RecoveryPreview.unavailable(
            status=RecoveryStatus.UNSUPPORTED_SCHEMA,
            wordlist_path=wordlist_path,
            detail=journal_result.detail or status.value,
            can_discard=True,
            preview_fingerprint=journal_result.content_digest or "unsupported",
        )

    journal = journal_result.journal
    assert journal is not None
    content_fingerprint = journal_result.content_digest or journal.transaction_id
    if status is JournalLoadStatus.VALID_COMPLETED:
        return RecoveryPreview(
            status=RecoveryStatus.COMPLETED_CLEANUP_PENDING,
            transaction_id=journal.transaction_id,
            command=journal.command,
            transaction_state=journal.state,
            started_at=journal.started,
            wordlist_path=wordlist_path,
            snapshot_directory=journal.snapshot_dir,
            items=(),
            recoverable_count=0,
            conflict_count=0,
            failure_count=0,
            warnings=(RECOVERY_CLEANUP_REMAINING,),
            can_recover=False,
            can_discard=True,
            can_cleanup=True,
            snapshots_valid=True,
            preview_fingerprint=content_fingerprint,
            journal_summary=journal_payload(journal),
            detail="Only cleanup is required.",
        )

    plans = plan_recovery_from_journal(journal)
    items = tuple(
        RecoveryItemPreview(
            name=plan.name,
            path=plan.path,
            current_state=plan.current_state,
            recovery_action=plan.recovery_action,
            status=plan.status,
            detail=plan.detail,
            existed_before=plan.existed_before,
            write_started=plan.write_started,
            write_completed=plan.write_completed,
            snapshot_valid=plan.snapshot_valid,
        )
        for plan in plans
    )
    recoverable_count = sum(1 for item in items if item.status == "ready")
    conflict_count = sum(1 for item in items if item.status == "conflict")
    failure_count = sum(1 for item in items if item.status == "failed")
    snapshots_valid = all(
        item.snapshot_valid or item.status in {"skipped", "conflict"} for item in items
    )
    warnings: list[str] = []
    if journal.state == JOURNAL_STATE_ROLLBACK_INCOMPLETE:
        warnings.append("Automatic rollback was incomplete.")
    if failure_count:
        warnings.append(f"{failure_count} item(s) have invalid snapshots.")
    if conflict_count:
        warnings.append(f"{conflict_count} item(s) have external conflicts.")

    if journal.state == JOURNAL_STATE_ROLLBACK_INCOMPLETE:
        recovery_status = RecoveryStatus.RECOVERY_IN_PROGRESS
    elif conflict_count:
        recovery_status = RecoveryStatus.CONFLICTED
    else:
        recovery_status = RecoveryStatus.RECOVERABLE

    can_recover = recoverable_count > 0 and snapshots_valid and failure_count == 0
    # Crash between journal create and first write: every item is "skipped",
    # can_recover is false, and without discard the dashboard stays permanently blocked.
    writes_started = any(item.write_started or item.write_completed for item in items)
    inert_unfinished = (
        recovery_status is RecoveryStatus.RECOVERABLE
        and recoverable_count == 0
        and conflict_count == 0
        and failure_count == 0
        and not writes_started
    )
    if inert_unfinished:
        warnings.append(
            RECOVERY_INERT_WARNING,
        )
    return RecoveryPreview(
        status=recovery_status,
        transaction_id=journal.transaction_id,
        command=journal.command,
        transaction_state=journal.state,
        started_at=journal.started,
        wordlist_path=wordlist_path,
        snapshot_directory=journal.snapshot_dir,
        items=items,
        recoverable_count=recoverable_count,
        conflict_count=conflict_count,
        failure_count=failure_count,
        warnings=tuple(warnings),
        can_recover=can_recover,
        can_discard=inert_unfinished,
        can_cleanup=False,
        snapshots_valid=snapshots_valid,
        preview_fingerprint=content_fingerprint,
        journal_summary=journal_payload(journal),
        detail=RECOVERY_INERT_DETAIL if inert_unfinished else None,
    )
