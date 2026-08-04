"""Recovery preview and execution."""

from __future__ import annotations

from ...exit_codes import ExitCode
from ...push_journal import JournalLoadStatus
from .. import _operation_deps
from ..builders import build_recovery_preview
from ..event_helpers import build_technical_event
from ..event_metadata import EventReason
from ..events import (
    EventCategory,
    EventId,
    EventPhase,
    EventSeverity,
    EventSink,
    OperationKind,
)
from ..reports import RecoveryExecution, RecoveryOutcome, RecoveryPreview, RecoveryStatus
from ..requests import RecoveryRequest
from ._shared import emit_technical, make_operation_emitter
from .context import ApplicationContext


def _emit_recovery_terminal(
    emitter,
    *,
    correlation_id: str,
    event_id: EventId,
    reason: EventReason | None = None,
    outcome: RecoveryOutcome | None = None,
    severity: EventSeverity = EventSeverity.ERROR,
) -> None:
    emit_technical(
        emitter,
        build_technical_event(
            event_id=event_id,
            operation=OperationKind.RECOVER,
            category=EventCategory.RECOVERY,
            severity=severity,
            phase=EventPhase.COMPLETED,
            correlation_id=correlation_id,
            reason=reason,
            outcome=outcome,
        ),
    )


class RecoveryService:
    def __init__(self, ctx: ApplicationContext) -> None:
        self._ctx = ctx

    def inspect_recovery(self, request: RecoveryRequest) -> RecoveryPreview:
        validated = self._ctx.runtime.validated(
            request.project,
            validate_journal_wordlist=True,
        )
        return build_recovery_preview(validated)

    def execute_recovery(
        self,
        request: RecoveryRequest,
        preview: RecoveryPreview,
        *,
        confirmed_transaction_id: str,
        dry_run: bool = False,
        event_sink: EventSink | None = None,
    ) -> RecoveryExecution:
        correlation_id = preview.preview_fingerprint
        emitter = make_operation_emitter(event_sink)

        if confirmed_transaction_id != preview.preview_fingerprint:
            _emit_recovery_terminal(
                emitter,
                correlation_id=correlation_id,
                event_id=EventId.RECOVERY_FAILED,
                reason=EventReason.CONFIRMATION_MISMATCH,
                outcome=RecoveryOutcome.FAILED,
            )
            return RecoveryExecution(
                preview=preview,
                result=ExitCode.PUSH_ABORT,
                outcome=RecoveryOutcome.FAILED,
                message="Recovery confirmation does not match the current preview.",
            )
        if not preview.can_recover:
            return RecoveryExecution(
                preview=preview,
                result=ExitCode.PUSH_ABORT,
                outcome=RecoveryOutcome.FAILED,
                message="Recovery is not available for this preview.",
            )

        emit_technical(
            emitter,
            build_technical_event(
                event_id=EventId.RECOVERY_VALIDATING,
                operation=OperationKind.RECOVER,
                category=EventCategory.RECOVERY,
                severity=EventSeverity.INFO,
                phase=EventPhase.PREPARING,
                correlation_id=correlation_id,
            ),
        )
        with self._ctx.runtime.mutation_scope(
            request.project,
            "recover",
            allow_unfinished_journal=True,
            json_output=request.json_output,
        ) as scope:
            if isinstance(scope, int):
                emit_technical(
                    emitter,
                    build_technical_event(
                        event_id=EventId.RECOVERY_BLOCKED,
                        operation=OperationKind.RECOVER,
                        category=EventCategory.SAFETY,
                        severity=EventSeverity.ERROR,
                        phase=EventPhase.EXECUTING,
                        correlation_id=correlation_id,
                        outcome=RecoveryOutcome.FAILED,
                    ),
                )
                return RecoveryExecution(
                    preview=preview,
                    result=ExitCode(scope),
                    outcome=RecoveryOutcome.FAILED,
                    message="Recovery could not acquire a safe execution context.",
                )

            emit_technical(
                emitter,
                build_technical_event(
                    event_id=EventId.RECOVERY_LOCK_ACQUIRED,
                    operation=OperationKind.RECOVER,
                    category=EventCategory.LIFECYCLE,
                    severity=EventSeverity.SUCCESS,
                    phase=EventPhase.EXECUTING,
                    correlation_id=correlation_id,
                ),
            )
            journal_result = scope.journal_result
            if journal_result.status is not JournalLoadStatus.VALID_IN_PROGRESS:
                return RecoveryExecution(
                    preview=preview,
                    result=ExitCode.PUSH_ABORT,
                    outcome=RecoveryOutcome.FAILED,
                    message="Recovery journal is no longer in progress.",
                )
            if journal_result.content_digest != preview.preview_fingerprint:
                return RecoveryExecution(
                    preview=preview,
                    result=ExitCode.PUSH_ABORT,
                    outcome=RecoveryOutcome.FAILED,
                    message="Recovery journal changed after preview.",
                )
            journal = journal_result.journal
            assert journal is not None
            if journal.transaction_id != preview.transaction_id:
                return RecoveryExecution(
                    preview=preview,
                    result=ExitCode.PUSH_ABORT,
                    outcome=RecoveryOutcome.FAILED,
                    message="Recovery journal changed after preview.",
                )

            emit_technical(
                emitter,
                build_technical_event(
                    event_id=EventId.RECOVERY_SNAPSHOTS_VALIDATED,
                    operation=OperationKind.RECOVER,
                    category=EventCategory.RECOVERY,
                    severity=EventSeverity.SUCCESS,
                    phase=EventPhase.EXECUTING,
                    correlation_id=correlation_id,
                ),
            )
            emit_technical(
                emitter,
                build_technical_event(
                    event_id=EventId.RECOVERY_CONFLICTS_CHECKED,
                    operation=OperationKind.RECOVER,
                    category=EventCategory.RECOVERY,
                    severity=EventSeverity.INFO,
                    phase=EventPhase.EXECUTING,
                    correlation_id=correlation_id,
                ),
            )
            total = max(len(preview.items), 1)
            for index, item in enumerate(preview.items, start=1):
                if item.status != "ready":
                    continue
                if item.name == "wordlist":
                    event_id = EventId.RECOVERY_WORDLIST_RESTORE_STARTED
                elif not item.existed_before and item.write_started:
                    event_id = EventId.RECOVERY_TARGET_REMOVE_STARTED
                else:
                    event_id = EventId.RECOVERY_TARGET_RESTORE_STARTED
                emit_technical(
                    emitter,
                    build_technical_event(
                        event_id=event_id,
                        operation=OperationKind.RECOVER,
                        category=EventCategory.RECOVERY,
                        severity=EventSeverity.INFO,
                        phase=EventPhase.EXECUTING,
                        correlation_id=correlation_id,
                        target_id=item.name,
                        completed=index,
                        total=total,
                    ),
                )

            result = _operation_deps.recover_from_journal(journal, dry_run=dry_run)
            incomplete = bool(result.failed or result.conflicts)
            if dry_run:
                outcome = (
                    RecoveryOutcome.CONFLICTED
                    if result.conflicts
                    else RecoveryOutcome.RECOVERED
                    if not incomplete
                    else RecoveryOutcome.RECOVERY_INCOMPLETE
                )
                return RecoveryExecution(
                    preview=preview,
                    result=result,
                    outcome=outcome,
                    message="Recovery dry-run completed.",
                    warnings=preview.warnings,
                    restored=result.restored,
                    skipped=result.skipped,
                    conflicts=result.conflicts,
                    failed=result.failed,
                )
            if incomplete:
                outcome = (
                    RecoveryOutcome.CONFLICTED
                    if result.conflicts
                    else RecoveryOutcome.RECOVERY_INCOMPLETE
                )
                emit_technical(
                    emitter,
                    build_technical_event(
                        event_id=EventId.RECOVERY_FAILED,
                        operation=OperationKind.RECOVER,
                        category=EventCategory.RECOVERY,
                        severity=EventSeverity.ERROR,
                        phase=EventPhase.EXECUTING,
                        correlation_id=correlation_id,
                        outcome=outcome,
                    ),
                )
                return RecoveryExecution(
                    preview=preview,
                    result=result,
                    outcome=outcome,
                    message=(
                        "Recovery stopped safely due to conflicts."
                        if result.conflicts
                        else "Recovery is incomplete."
                    ),
                    warnings=preview.warnings,
                    restored=result.restored,
                    skipped=result.skipped,
                    conflicts=result.conflicts,
                    failed=result.failed,
                )

            cleanup_result = _operation_deps.cleanup_after_successful_recovery(journal)
            if not cleanup_result.ok:
                emit_technical(
                    emitter,
                    build_technical_event(
                        event_id=EventId.RECOVERY_FAILED,
                        operation=OperationKind.RECOVER,
                        category=EventCategory.RECOVERY,
                        severity=EventSeverity.ERROR,
                        phase=EventPhase.FINALIZING,
                        correlation_id=correlation_id,
                        reason=EventReason.CLEANUP_FAILED,
                        outcome=RecoveryOutcome.RECOVERY_INCOMPLETE,
                    ),
                )
                return RecoveryExecution(
                    preview=preview,
                    result=result,
                    outcome=RecoveryOutcome.RECOVERY_INCOMPLETE,
                    message=(
                        cleanup_result.detail or "Recovery succeeded but cleanup artifacts remain."
                    ),
                    warnings=preview.warnings,
                    restored=result.restored,
                    skipped=result.skipped,
                    conflicts=result.conflicts,
                    failed=result.failed,
                )
            emit_technical(
                emitter,
                build_technical_event(
                    event_id=EventId.RECOVERY_CLEANUP_STARTED,
                    operation=OperationKind.RECOVER,
                    category=EventCategory.RECOVERY,
                    severity=EventSeverity.SUCCESS,
                    phase=EventPhase.FINALIZING,
                    correlation_id=correlation_id,
                ),
            )
            emit_technical(
                emitter,
                build_technical_event(
                    event_id=EventId.RECOVERY_COMPLETED,
                    operation=OperationKind.RECOVER,
                    category=EventCategory.RECOVERY,
                    severity=EventSeverity.SUCCESS,
                    phase=EventPhase.COMPLETED,
                    correlation_id=correlation_id,
                    outcome=RecoveryOutcome.RECOVERED,
                ),
            )
            outcome = (
                RecoveryOutcome.RECOVERED_WITH_WARNINGS
                if result.skipped and result.restored
                else RecoveryOutcome.RECOVERED
            )
            message = (
                f"{len(result.restored)} file(s) restored"
                if result.restored
                else "Recovery completed with no file changes"
            )
            return RecoveryExecution(
                preview=preview,
                result=result,
                outcome=outcome,
                message=message,
                warnings=preview.warnings,
                restored=result.restored,
                skipped=result.skipped,
                conflicts=result.conflicts,
                failed=result.failed,
            )

    def execute_recovery_cleanup(
        self,
        request: RecoveryRequest,
        preview: RecoveryPreview,
        *,
        confirmed_transaction_id: str,
        event_sink: EventSink | None = None,
    ) -> RecoveryExecution:
        correlation_id = preview.preview_fingerprint
        emitter = make_operation_emitter(event_sink)

        if confirmed_transaction_id != preview.preview_fingerprint:
            _emit_recovery_terminal(
                emitter,
                correlation_id=correlation_id,
                event_id=EventId.RECOVERY_FAILED,
                reason=EventReason.CONFIRMATION_MISMATCH,
                outcome=RecoveryOutcome.FAILED,
            )
            return RecoveryExecution(
                preview=preview,
                result=ExitCode.PUSH_ABORT,
                outcome=RecoveryOutcome.FAILED,
                message="Cleanup confirmation does not match the current preview.",
            )
        if preview.status is not RecoveryStatus.COMPLETED_CLEANUP_PENDING:
            return RecoveryExecution(
                preview=preview,
                result=ExitCode.PUSH_ABORT,
                outcome=RecoveryOutcome.FAILED,
                message="Cleanup is not available for this preview.",
            )
        with self._ctx.runtime.mutation_scope(
            request.project,
            "recover",
            allow_unfinished_journal=True,
            json_output=request.json_output,
        ) as scope:
            if isinstance(scope, int):
                return RecoveryExecution(
                    preview=preview,
                    result=ExitCode(scope),
                    outcome=RecoveryOutcome.FAILED,
                    message="Cleanup could not acquire a safe execution context.",
                )
            wordlist = scope.context.wordlist_file
            journal_result = scope.journal_result
            if journal_result.status is not JournalLoadStatus.VALID_COMPLETED:
                return RecoveryExecution(
                    preview=preview,
                    result=ExitCode.PUSH_ABORT,
                    outcome=RecoveryOutcome.FAILED,
                    message="Completed journal is no longer present.",
                )
            if journal_result.content_digest != preview.preview_fingerprint:
                return RecoveryExecution(
                    preview=preview,
                    result=ExitCode.PUSH_ABORT,
                    outcome=RecoveryOutcome.FAILED,
                    message="Completed journal changed after preview.",
                )
            journal = journal_result.journal
            assert journal is not None
            if journal.transaction_id != preview.transaction_id:
                return RecoveryExecution(
                    preview=preview,
                    result=ExitCode.PUSH_ABORT,
                    outcome=RecoveryOutcome.FAILED,
                    message="Completed journal changed after preview.",
                )
            discard_result = _operation_deps.discard_completed_journal(wordlist)
            if not discard_result.ok:
                return RecoveryExecution(
                    preview=preview,
                    result=ExitCode.PUSH_ABORT,
                    outcome=RecoveryOutcome.FAILED,
                    message=discard_result.detail or "Cleanup could not remove recovery artifacts.",
                )
            emit_technical(
                emitter,
                build_technical_event(
                    event_id=EventId.RECOVERY_CLEANUP_COMPLETED,
                    operation=OperationKind.RECOVER,
                    category=EventCategory.RECOVERY,
                    severity=EventSeverity.SUCCESS,
                    phase=EventPhase.COMPLETED,
                    correlation_id=correlation_id,
                    outcome=RecoveryOutcome.CLEANUP_COMPLETED,
                ),
            )
            return RecoveryExecution(
                preview=preview,
                result=ExitCode.OK,
                outcome=RecoveryOutcome.CLEANUP_COMPLETED,
                message="Remaining recovery artifacts were removed.",
            )

    def execute_recovery_discard(
        self,
        request: RecoveryRequest,
        preview: RecoveryPreview,
        *,
        confirmed_transaction_id: str,
        event_sink: EventSink | None = None,
    ) -> RecoveryExecution:
        correlation_id = preview.preview_fingerprint
        emitter = make_operation_emitter(event_sink)

        if confirmed_transaction_id != preview.preview_fingerprint:
            _emit_recovery_terminal(
                emitter,
                correlation_id=correlation_id,
                event_id=EventId.RECOVERY_FAILED,
                reason=EventReason.CONFIRMATION_MISMATCH,
                outcome=RecoveryOutcome.FAILED,
            )
            return RecoveryExecution(
                preview=preview,
                result=ExitCode.PUSH_ABORT,
                outcome=RecoveryOutcome.FAILED,
                message="Discard confirmation does not match the current preview.",
            )
        if not preview.can_discard:
            return RecoveryExecution(
                preview=preview,
                result=ExitCode.PUSH_ABORT,
                outcome=RecoveryOutcome.FAILED,
                message="Discard is not available for this preview.",
            )
        with self._ctx.runtime.mutation_scope(
            request.project,
            "recover",
            allow_unfinished_journal=True,
            json_output=request.json_output,
        ) as scope:
            if isinstance(scope, int):
                return RecoveryExecution(
                    preview=preview,
                    result=ExitCode(scope),
                    outcome=RecoveryOutcome.FAILED,
                    message="Discard could not acquire a safe execution context.",
                )
            wordlist = scope.context.wordlist_file
            journal_result = scope.journal_result
            if preview.status is RecoveryStatus.CORRUPT_JOURNAL:
                if journal_result.status is JournalLoadStatus.ABSENT:
                    _emit_recovery_terminal(
                        emitter,
                        correlation_id=correlation_id,
                        event_id=EventId.RECOVERY_DISCARDED,
                        severity=EventSeverity.SUCCESS,
                        outcome=RecoveryOutcome.DISCARDED,
                    )
                    return RecoveryExecution(
                        preview=preview,
                        result=ExitCode.OK,
                        outcome=RecoveryOutcome.DISCARDED,
                        message="Recovery metadata discarded.",
                    )
                if journal_result.status is not JournalLoadStatus.CORRUPT:
                    return RecoveryExecution(
                        preview=preview,
                        result=ExitCode.PUSH_ABORT,
                        outcome=RecoveryOutcome.FAILED,
                        message="Corrupt journal is no longer present as reviewed.",
                    )
                if journal_result.content_digest != preview.preview_fingerprint:
                    return RecoveryExecution(
                        preview=preview,
                        result=ExitCode.PUSH_ABORT,
                        outcome=RecoveryOutcome.FAILED,
                        message="Corrupt journal changed after preview.",
                    )
                journal_ok, detail = _operation_deps.safe_discard_journal_file(wordlist)
                if not journal_ok:
                    return RecoveryExecution(
                        preview=preview,
                        result=ExitCode.PUSH_ABORT,
                        outcome=RecoveryOutcome.FAILED,
                        message=detail or "Discard could not remove recovery metadata.",
                    )
            else:
                if (
                    journal_result.status is not JournalLoadStatus.VALID_COMPLETED
                    or journal_result.content_digest != preview.preview_fingerprint
                ):
                    return RecoveryExecution(
                        preview=preview,
                        result=ExitCode.PUSH_ABORT,
                        outcome=RecoveryOutcome.FAILED,
                        message="Completed journal changed after preview.",
                    )
                discard_result = _operation_deps.discard_completed_journal(wordlist)
                if not discard_result.ok:
                    return RecoveryExecution(
                        preview=preview,
                        result=ExitCode.PUSH_ABORT,
                        outcome=RecoveryOutcome.FAILED,
                        message=discard_result.detail
                        or "Discard could not remove recovery metadata.",
                    )
            _emit_recovery_terminal(
                emitter,
                correlation_id=correlation_id,
                event_id=EventId.RECOVERY_DISCARDED,
                severity=EventSeverity.SUCCESS,
                outcome=RecoveryOutcome.DISCARDED,
            )
            return RecoveryExecution(
                preview=preview,
                result=ExitCode.OK,
                outcome=RecoveryOutcome.DISCARDED,
                message="Recovery metadata discarded.",
            )
