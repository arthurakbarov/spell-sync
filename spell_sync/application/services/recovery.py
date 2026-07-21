"""Recovery preview and execution."""

from __future__ import annotations

from ...exit_codes import ExitCode
from ...push_journal import JournalLoadStatus
from .. import _operation_deps
from ..builders import build_recovery_preview
from ..events import EventLevel, EventSink, OperationEvent, OperationKind
from ..reports import RecoveryExecution, RecoveryOutcome, RecoveryPreview, RecoveryStatus
from ..requests import RecoveryRequest
from ._shared import emit
from .context import ApplicationContext


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
        if confirmed_transaction_id != preview.preview_fingerprint:
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

        emit(
            event_sink,
            OperationEvent(OperationKind.RECOVER, "validating_journal", "Validating journal"),
        )
        with self._ctx.runtime.mutation_scope(
            request.project,
            "recover",
            allow_unfinished_journal=True,
            json_output=request.json_output,
        ) as scope:
            if isinstance(scope, int):
                emit(
                    event_sink,
                    OperationEvent(
                        OperationKind.RECOVER,
                        "failed",
                        "Recovery blocked by lock or configuration",
                        level=EventLevel.ERROR,
                    ),
                )
                return RecoveryExecution(
                    preview=preview,
                    result=ExitCode(scope),
                    outcome=RecoveryOutcome.FAILED,
                    message="Recovery could not acquire a safe execution context.",
                )

            emit(
                event_sink,
                OperationEvent(
                    OperationKind.RECOVER,
                    "acquiring_lock",
                    "Operation lock acquired",
                    level=EventLevel.SUCCESS,
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
            journal = journal_result.journal
            assert journal is not None
            if journal.transaction_id != preview.transaction_id:
                return RecoveryExecution(
                    preview=preview,
                    result=ExitCode.PUSH_ABORT,
                    outcome=RecoveryOutcome.FAILED,
                    message="Recovery journal changed after preview.",
                )

            emit(
                event_sink,
                OperationEvent(
                    OperationKind.RECOVER,
                    "validating_snapshots",
                    "Validating recovery snapshots",
                    level=EventLevel.SUCCESS,
                ),
            )
            emit(
                event_sink,
                OperationEvent(
                    OperationKind.RECOVER,
                    "checking_conflicts",
                    "Checking recovery conflicts",
                ),
            )
            total = max(len(preview.items), 1)
            for index, item in enumerate(preview.items, start=1):
                if item.status != "ready":
                    continue
                stage = "restoring_wordlist" if item.name == "wordlist" else "restoring_target"
                if not item.existed_before and item.write_started:
                    stage = "removing_created_target"
                emit(
                    event_sink,
                    OperationEvent(
                        OperationKind.RECOVER,
                        stage,
                        f"Recovering {item.name}",
                        target=item.name,
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
                emit(
                    event_sink,
                    OperationEvent(
                        OperationKind.RECOVER,
                        "failed",
                        "Recovery incomplete",
                        level=EventLevel.ERROR,
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
                emit(
                    event_sink,
                    OperationEvent(
                        OperationKind.RECOVER,
                        "failed",
                        cleanup_result.detail or "Recovery cleanup incomplete",
                        level=EventLevel.ERROR,
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
            emit(
                event_sink,
                OperationEvent(
                    OperationKind.RECOVER,
                    "cleaning_artifacts",
                    "Cleaning recovery artifacts",
                    level=EventLevel.SUCCESS,
                ),
            )
            emit(
                event_sink,
                OperationEvent(
                    OperationKind.RECOVER,
                    "completed",
                    "Recovery completed",
                    level=EventLevel.SUCCESS,
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
        if confirmed_transaction_id != preview.preview_fingerprint:
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
            discard_result = _operation_deps.discard_completed_journal(wordlist)
            if not discard_result.ok:
                return RecoveryExecution(
                    preview=preview,
                    result=ExitCode.PUSH_ABORT,
                    outcome=RecoveryOutcome.FAILED,
                    message=discard_result.detail or "Cleanup could not remove recovery artifacts.",
                )
            emit(
                event_sink,
                OperationEvent(
                    OperationKind.RECOVER,
                    "cleaning_artifacts",
                    "Cleanup completed",
                    level=EventLevel.SUCCESS,
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
        if confirmed_transaction_id != preview.preview_fingerprint:
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
            if preview.status is RecoveryStatus.CORRUPT_JOURNAL:
                journal_ok, detail = _operation_deps.safe_discard_journal_file(wordlist)
                if not journal_ok:
                    return RecoveryExecution(
                        preview=preview,
                        result=ExitCode.PUSH_ABORT,
                        outcome=RecoveryOutcome.FAILED,
                        message=detail or "Discard could not remove recovery metadata.",
                    )
            else:
                discard_result = _operation_deps.discard_completed_journal(wordlist)
                if not discard_result.ok:
                    return RecoveryExecution(
                        preview=preview,
                        result=ExitCode.PUSH_ABORT,
                        outcome=RecoveryOutcome.FAILED,
                        message=discard_result.detail
                        or "Discard could not remove recovery metadata.",
                    )
            return RecoveryExecution(
                preview=preview,
                result=ExitCode.OK,
                outcome=RecoveryOutcome.DISCARDED,
                message="Recovery metadata discarded.",
            )
