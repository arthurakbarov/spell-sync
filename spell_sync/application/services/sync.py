"""Pull and Push synchronization orchestration."""

from __future__ import annotations

from pathlib import Path

from ...application.project_resolution import effective_push_strict
from ...exit_codes import ExitCode
from ...mutation_guards import invalid_config_exit_from_scope
from ...push_abort import PushAbort
from ...push_journal import JournalLoadStatus
from ...push_prepared import PreparedPush
from ...settings import config_blocks_mutating
from ...sync_models import DictionaryDiff, PushResult
from ...sync_run import SyncRun
from .. import _operation_deps
from ..builders import build_pull_add_from_preview, build_push_preview
from ..event_helpers import (
    build_technical_event,
    push_abort_reason_to_event_reason,
    runtime_changed_reason,
)
from ..event_metadata import EventReason
from ..events import (
    EventCategory,
    EventEmitter,
    EventId,
    EventPhase,
    EventSeverity,
    EventSink,
    OperationKind,
)
from ..operation_explanations import build_push_target_updates
from ..reports import OperationOutcome, PullExecution, PullPreview, PushExecution, PushPreview
from ..requests import PullRequest, PushRequest, RecoveryRequest
from ._shared import (
    RUNTIME_CHANGED_MESSAGE,
    emit_technical,
    make_operation_emitter,
    running_app_skip_reasons_for,
    runtime_identity_matches,
)
from .context import ApplicationContext


class SyncService:
    def __init__(self, ctx: ApplicationContext) -> None:
        self._ctx = ctx

    def _effective_push_strict(self, request: PushRequest) -> bool:
        resolved = self._ctx.runtime.resolve_read(request.project)
        return effective_push_strict(request, settings=resolved.context.settings)

    def mutating_config_exit_code(
        self,
        request: PullRequest | PushRequest | RecoveryRequest,
        command: str,
    ) -> int | None:
        """Return an exit code when config blocks mutation; emit JSON when requested."""
        strict = False
        if isinstance(request, PushRequest):
            strict = self._effective_push_strict(request)
        resolved = self._ctx.runtime.resolve_read(request.project, strict_push=strict)
        if not config_blocks_mutating(resolved.config_result):
            return None
        return invalid_config_exit_from_scope(
            command,
            resolved.config_result,
            json_output=request.json_output,
        )

    def load_push_preview(self, request: PushRequest) -> PushPreview:
        strict = self._effective_push_strict(request)
        run = self._ctx.runtime.sync_run(request.project, strict_push=strict)
        wordlist_error = run.check_wordlist()
        if wordlist_error is not None:
            return build_push_preview(None, wordlist_error=wordlist_error)
        prepared = self._prepare_push_for_run(run)
        if isinstance(prepared, ExitCode):
            return build_push_preview(None, prepare_error=prepared)
        return build_push_preview(prepared)

    def load_push_removals(self, request: PushRequest) -> tuple[DictionaryDiff, ...]:
        strict = self._effective_push_strict(request)
        run = self._ctx.runtime.sync_run(request.project, strict_push=strict)
        return tuple(diff for diff in run.status_diffs(verbose=True) if diff.to_remove > 0)

    def load_push_plan(
        self,
        request: PushRequest,
        *,
        verbose: bool = False,
    ) -> tuple[PushPreview, tuple[DictionaryDiff, ...], PushResult | ExitCode]:
        strict = self._effective_push_strict(request)
        run = self._ctx.runtime.sync_run(request.project, strict_push=strict)
        preview = self.load_push_preview(request)
        diffs = tuple(run.status_diffs(verbose=verbose))
        if not preview.is_executable or preview.prepared is None:
            error = preview.prepare_error or preview.wordlist_error or ExitCode.PUSH_ABORT
            return preview, diffs, error
        skip_names: frozenset[str] = frozenset()
        result = run.plan_push(skip_names=skip_names)
        return preview, diffs, result

    def execute_push_dry_run(self, request: PushRequest, preview: PushPreview) -> PushExecution:
        prepared = preview.prepared
        if prepared is None or not preview.is_executable:
            return PushExecution(
                prepared=prepared,
                result=ExitCode.PUSH_ABORT,
                outcome=OperationOutcome.FAILED,
                message="Push preview is not executable.",
                plan_identifier=preview.plan_identifier,
                push_preview=preview,
            )
        strict_override = request.strict_override
        with self._ctx.runtime.mutation_scope(
            request.project,
            "push",
            strict_push_override=strict_override,
            json_output=request.json_output,
        ) as scope:
            if isinstance(scope, int):
                return PushExecution(
                    prepared=prepared,
                    result=ExitCode(scope),
                    outcome=OperationOutcome.FAILED,
                    message="Push could not acquire a safe execution context.",
                    plan_identifier=preview.plan_identifier,
                    push_preview=preview,
                )
            if not runtime_identity_matches(prepared.runtime_identity, scope.identity):
                return PushExecution(
                    prepared=prepared,
                    result=ExitCode.PUSH_ABORT,
                    outcome=OperationOutcome.STOPPED_SAFELY,
                    message=RUNTIME_CHANGED_MESSAGE,
                    plan_identifier=preview.plan_identifier,
                    push_preview=preview,
                )
            run = SyncRun(context=scope.context)
            result = self._execute_push_for_run(
                run,
                prepared,
                dry_run=True,
                event_sink=None,
                correlation_id=preview.plan_identifier,
            )
            execution = self.push_execution_from_result(prepared, result)
            return PushExecution(
                prepared=execution.prepared,
                result=execution.result,
                outcome=execution.outcome,
                message=execution.message,
                warnings=execution.warnings,
                target_updates=execution.target_updates,
                recovery_required=execution.recovery_required,
                plan_identifier=preview.plan_identifier,
                push_preview=preview,
            )

    def prepare_pull(self, request: PullRequest) -> PullPreview:
        run = self._ctx.runtime.sync_run(request.project)
        if request.add_from is not None:
            return build_pull_add_from_preview(run, request.add_from)
        return _operation_deps.build_pull_preview(run)

    def execute_pull(
        self,
        request: PullRequest,
        preview: PullPreview,
        *,
        confirmed_plan_id: str,
        event_sink: EventSink | None = None,
    ) -> PullExecution:
        correlation_id = preview.plan_identifier
        emitter = make_operation_emitter(event_sink)

        if confirmed_plan_id != preview.plan_identifier:
            emit_technical(
                emitter,
                build_technical_event(
                    event_id=EventId.PULL_BLOCKED,
                    operation=OperationKind.PULL,
                    category=EventCategory.SAFETY,
                    severity=EventSeverity.ERROR,
                    phase=EventPhase.COMPLETED,
                    correlation_id=correlation_id,
                    reason=EventReason.CONFIRMATION_MISMATCH,
                    outcome=OperationOutcome.FAILED,
                ),
            )
            return PullExecution(
                preview=preview,
                result=ExitCode.PUSH_ABORT,
                outcome=OperationOutcome.FAILED,
                message="Pull confirmation does not match the current preview.",
            )
        if not preview.is_executable:
            emit_technical(
                emitter,
                build_technical_event(
                    event_id=EventId.PULL_BLOCKED,
                    operation=OperationKind.PULL,
                    category=EventCategory.SAFETY,
                    severity=EventSeverity.ERROR,
                    phase=EventPhase.COMPLETED,
                    correlation_id=correlation_id,
                    reason=EventReason.PREVIEW_NOT_EXECUTABLE,
                    outcome=OperationOutcome.FAILED,
                ),
            )
            return PullExecution(
                preview=preview,
                result=preview.wordlist_error or preview.prepare_error or ExitCode.PUSH_ABORT,
                outcome=OperationOutcome.FAILED,
                message="Pull preview is not executable.",
            )

        emit_technical(
            emitter,
            build_technical_event(
                event_id=EventId.PULL_VALIDATING,
                operation=OperationKind.PULL,
                category=EventCategory.LIFECYCLE,
                severity=EventSeverity.INFO,
                phase=EventPhase.PREPARING,
                correlation_id=correlation_id,
            ),
        )
        with self._ctx.runtime.mutation_scope(
            request.project,
            "pull",
            json_output=request.json_output,
        ) as scope:
            if isinstance(scope, int):
                emit_technical(
                    emitter,
                    build_technical_event(
                        event_id=EventId.PULL_BLOCKED,
                        operation=OperationKind.PULL,
                        category=EventCategory.SAFETY,
                        severity=EventSeverity.ERROR,
                        phase=EventPhase.PREPARING,
                        correlation_id=correlation_id,
                        outcome=OperationOutcome.FAILED,
                    ),
                )
                return PullExecution(
                    preview=preview,
                    result=ExitCode(scope),
                    outcome=OperationOutcome.FAILED,
                    message="Pull could not acquire a safe execution context.",
                )

            emit_technical(
                emitter,
                build_technical_event(
                    event_id=EventId.PULL_LOCK_ACQUIRED,
                    operation=OperationKind.PULL,
                    category=EventCategory.LIFECYCLE,
                    severity=EventSeverity.SUCCESS,
                    phase=EventPhase.EXECUTING,
                    correlation_id=correlation_id,
                ),
            )
            run = SyncRun(context=scope.context)
            if preview.runtime_identity is not None and not runtime_identity_matches(
                preview.runtime_identity, scope.identity
            ):
                emit_technical(
                    emitter,
                    build_technical_event(
                        event_id=EventId.PULL_RUNTIME_CHANGED,
                        operation=OperationKind.PULL,
                        category=EventCategory.SAFETY,
                        severity=EventSeverity.ERROR,
                        phase=EventPhase.EXECUTING,
                        correlation_id=correlation_id,
                        reason=runtime_changed_reason(),
                        outcome=OperationOutcome.STOPPED_SAFELY,
                    ),
                )
                return PullExecution(
                    preview=preview,
                    result=ExitCode.PUSH_ABORT,
                    outcome=OperationOutcome.STOPPED_SAFELY,
                    message=RUNTIME_CHANGED_MESSAGE,
                    warnings=preview.warnings,
                )
            if Path(preview.wordlist_path).resolve() != Path(run.wordlist_str).resolve():
                emit_technical(
                    emitter,
                    build_technical_event(
                        event_id=EventId.PULL_WORDLIST_MISMATCH,
                        operation=OperationKind.PULL,
                        category=EventCategory.SAFETY,
                        severity=EventSeverity.ERROR,
                        phase=EventPhase.EXECUTING,
                        correlation_id=correlation_id,
                        outcome=OperationOutcome.FAILED,
                    ),
                )
                return PullExecution(
                    preview=preview,
                    result=ExitCode.PUSH_ABORT,
                    outcome=OperationOutcome.FAILED,
                    message="Pull preview does not match the active wordlist.",
                )

            emit_technical(
                emitter,
                build_technical_event(
                    event_id=EventId.PULL_PLAN_VERIFIED,
                    operation=OperationKind.PULL,
                    category=EventCategory.LIFECYCLE,
                    severity=EventSeverity.SUCCESS,
                    phase=EventPhase.EXECUTING,
                    correlation_id=correlation_id,
                ),
            )
            emit_technical(
                emitter,
                build_technical_event(
                    event_id=EventId.PULL_WRITE_STARTED,
                    operation=OperationKind.PULL,
                    category=EventCategory.TRANSACTION,
                    severity=EventSeverity.INFO,
                    phase=EventPhase.EXECUTING,
                    correlation_id=correlation_id,
                ),
            )
            result = run.execute_prepared_pull(
                merged_words=preview.merged_words,
                before_count=preview.before_count,
                after_count=preview.after_count,
                wordlist_fingerprint=preview.wordlist_fingerprint,
            )
            if isinstance(result, ExitCode):
                current = _operation_deps.file_content_hash(Path(run.wordlist_str))
                conflict = (
                    preview.wordlist_fingerprint is not None
                    and current is not None
                    and current != preview.wordlist_fingerprint
                )
                emit_technical(
                    emitter,
                    build_technical_event(
                        event_id=(
                            EventId.PULL_WORDLIST_CHANGED if conflict else EventId.PULL_WRITE_FAILED
                        ),
                        operation=OperationKind.PULL,
                        category=EventCategory.SAFETY if conflict else EventCategory.TRANSACTION,
                        severity=EventSeverity.ERROR,
                        phase=EventPhase.EXECUTING,
                        correlation_id=correlation_id,
                        outcome=(
                            OperationOutcome.STOPPED_SAFELY.value
                            if conflict
                            else OperationOutcome.FAILED.value
                        ),
                    ),
                )
                return PullExecution(
                    preview=preview,
                    result=result,
                    outcome=(
                        OperationOutcome.STOPPED_SAFELY if conflict else OperationOutcome.FAILED
                    ),
                    message=(
                        "Wordlist changed after the preview was created."
                        if conflict
                        else "Pull aborted — failed to write wordlist."
                    ),
                    warnings=preview.warnings,
                )

            emit_technical(
                emitter,
                build_technical_event(
                    event_id=EventId.PULL_COMPLETED,
                    operation=OperationKind.PULL,
                    category=EventCategory.LIFECYCLE,
                    severity=EventSeverity.SUCCESS,
                    phase=EventPhase.COMPLETED,
                    correlation_id=correlation_id,
                    outcome=OperationOutcome.COMPLETED,
                ),
            )
            before, after = result
            return PullExecution(
                preview=preview,
                result=(before, after),
                outcome=OperationOutcome.COMPLETED,
                message=f"wordlist: {before} -> {after} (+{after - before})",
                warnings=preview.warnings,
            )

    def _prepare_push_for_run(
        self,
        run: SyncRun,
        *,
        event_sink: EventSink | None = None,
        correlation_id: str | None = None,
    ) -> PreparedPush | ExitCode:
        emitter = make_operation_emitter(event_sink)
        emit_technical(
            emitter,
            build_technical_event(
                event_id=EventId.PUSH_BUILDING_PLAN,
                operation=OperationKind.PUSH,
                category=EventCategory.LIFECYCLE,
                severity=EventSeverity.INFO,
                phase=EventPhase.PREPARING,
                correlation_id=correlation_id,
            ),
        )
        skip_names: frozenset[str] = frozenset()
        prepared = run.prepare_push_operation(skip_names=skip_names)
        if isinstance(prepared, ExitCode):
            emit_technical(
                emitter,
                build_technical_event(
                    event_id=EventId.PUSH_PLAN_FAILED,
                    operation=OperationKind.PUSH,
                    category=EventCategory.LIFECYCLE,
                    severity=EventSeverity.ERROR,
                    phase=EventPhase.PREPARING,
                    correlation_id=correlation_id,
                    outcome=OperationOutcome.FAILED,
                ),
            )
        return prepared

    def _execute_push_for_run(
        self,
        run: SyncRun,
        prepared: PreparedPush,
        *,
        dry_run: bool,
        event_sink: EventSink | None = None,
        correlation_id: str | None = None,
    ) -> PushResult | ExitCode:
        emitter = make_operation_emitter(event_sink)
        conflict = _operation_deps.plan_fingerprint_conflict(prepared)
        if conflict is not None:
            emit_technical(
                emitter,
                build_technical_event(
                    event_id=EventId.PUSH_TARGET_CHANGED,
                    operation=OperationKind.PUSH,
                    category=EventCategory.SAFETY,
                    severity=EventSeverity.ERROR,
                    phase=EventPhase.EXECUTING,
                    correlation_id=correlation_id,
                    target_id=conflict,
                    outcome=OperationOutcome.STOPPED_SAFELY,
                ),
            )
            return ExitCode.PUSH_ABORT

        emit_technical(
            emitter,
            build_technical_event(
                event_id=EventId.PUSH_PLAN_VERIFIED,
                operation=OperationKind.PUSH,
                category=EventCategory.LIFECYCLE,
                severity=EventSeverity.SUCCESS,
                phase=EventPhase.EXECUTING,
                correlation_id=correlation_id,
            ),
        )
        emit_technical(
            emitter,
            build_technical_event(
                event_id=(
                    EventId.PUSH_DRY_RUN_STARTED if dry_run else EventId.PUSH_EXECUTION_STARTED
                ),
                operation=OperationKind.PUSH,
                category=EventCategory.TRANSACTION,
                severity=EventSeverity.INFO,
                phase=EventPhase.EXECUTING,
                correlation_id=correlation_id,
            ),
        )
        if dry_run:
            result = run._run_push_transaction(dry_run=True, prepared=prepared)
        else:
            result = run.push_from_wordlist(prepared=prepared)
        if isinstance(result, PushResult):
            emit_technical(
                emitter,
                build_technical_event(
                    event_id=EventId.PUSH_COMPLETED,
                    operation=OperationKind.PUSH,
                    category=EventCategory.LIFECYCLE,
                    severity=EventSeverity.SUCCESS,
                    phase=EventPhase.COMPLETED,
                    correlation_id=correlation_id,
                    outcome=OperationOutcome.COMPLETED,
                ),
            )
        else:
            emit_technical(
                emitter,
                build_technical_event(
                    event_id=EventId.PUSH_FAILED,
                    operation=OperationKind.PUSH,
                    category=EventCategory.TRANSACTION,
                    severity=EventSeverity.ERROR,
                    phase=EventPhase.EXECUTING,
                    correlation_id=correlation_id,
                    outcome=OperationOutcome.FAILED,
                ),
            )
        return result

    def _run_push_for_run(
        self,
        run: SyncRun,
        prepared: PreparedPush,
        *,
        dry_run: bool,
        event_sink: EventSink | None = None,
        correlation_id: str | None = None,
    ) -> PushExecution:
        result = self._execute_push_for_run(
            run,
            prepared,
            dry_run=dry_run,
            event_sink=event_sink,
            correlation_id=correlation_id,
        )
        return self.push_execution_from_result(prepared, result)

    def pull_execution_from_result(
        self,
        preview: PullPreview,
        result: tuple[int, int] | ExitCode,
    ) -> PullExecution:
        if isinstance(result, ExitCode):
            return PullExecution(
                preview=preview,
                result=result,
                outcome=OperationOutcome.FAILED,
                message="Pull failed.",
                warnings=preview.warnings,
            )
        before, after = result
        return PullExecution(
            preview=preview,
            result=(before, after),
            outcome=OperationOutcome.COMPLETED,
            message=f"wordlist: {before} -> {after} (+{after - before})",
            warnings=preview.warnings,
        )

    def push_execution_from_result(
        self,
        prepared: PreparedPush,
        result: PushResult | ExitCode,
    ) -> PushExecution:
        preview: PushPreview | None = None
        updates: tuple = ()
        if prepared is not None:
            try:
                preview = build_push_preview(prepared)
                push_result = result if isinstance(result, PushResult) else None
                updates = build_push_target_updates(preview, push_result)
            except AttributeError:
                preview = None
                updates = ()
        if isinstance(result, ExitCode):
            return PushExecution(
                prepared=prepared,
                result=result,
                outcome=OperationOutcome.FAILED,
                message="Push failed.",
                target_updates=updates,
                push_preview=preview,
            )
        outcome = OperationOutcome.COMPLETED
        if result.skipped:
            outcome = OperationOutcome.COMPLETED_WITH_WARNINGS
        return PushExecution(
            prepared=prepared,
            result=result,
            outcome=outcome,
            message="Push completed.",
            target_updates=updates,
            push_preview=preview,
        )

    def execute_push_preview(
        self,
        request: PushRequest,
        preview: PushPreview,
        *,
        confirmed_plan_id: str,
        event_sink: EventSink | None = None,
    ) -> PushExecution:
        """Execute push using the exact PreparedPush from preview (no re-prepare)."""
        prepared = preview.prepared
        correlation_id = preview.plan_identifier
        emitter = make_operation_emitter(event_sink)

        if prepared is None or not preview.is_executable:
            return PushExecution(
                prepared=prepared,
                result=ExitCode.PUSH_ABORT,
                outcome=OperationOutcome.FAILED,
                message="Push preview is not executable.",
                plan_identifier=preview.plan_identifier,
                push_preview=preview,
            )
        if confirmed_plan_id != preview.plan_identifier:
            return PushExecution(
                prepared=prepared,
                result=ExitCode.PUSH_ABORT,
                outcome=OperationOutcome.FAILED,
                message="Push confirmation does not match the current preview.",
                plan_identifier=preview.plan_identifier,
                push_preview=preview,
            )

        updates = build_push_target_updates(preview, None)
        emit_technical(
            emitter,
            build_technical_event(
                event_id=EventId.PUSH_VALIDATING,
                operation=OperationKind.PUSH,
                category=EventCategory.LIFECYCLE,
                severity=EventSeverity.INFO,
                phase=EventPhase.PREPARING,
                correlation_id=correlation_id,
            ),
        )
        strict_override = request.strict_override
        with self._ctx.runtime.mutation_scope(
            request.project,
            "push",
            strict_push_override=strict_override,
            json_output=request.json_output,
        ) as scope:
            if isinstance(scope, int):
                emit_technical(
                    emitter,
                    build_technical_event(
                        event_id=EventId.PUSH_BLOCKED,
                        operation=OperationKind.PUSH,
                        category=EventCategory.SAFETY,
                        severity=EventSeverity.ERROR,
                        phase=EventPhase.PREPARING,
                        correlation_id=correlation_id,
                        outcome=OperationOutcome.FAILED,
                    ),
                )
                return PushExecution(
                    prepared=prepared,
                    result=ExitCode(scope),
                    outcome=OperationOutcome.FAILED,
                    message="Push could not acquire a safe execution context.",
                    target_updates=updates,
                    plan_identifier=preview.plan_identifier,
                )

            emit_technical(
                emitter,
                build_technical_event(
                    event_id=EventId.PUSH_LOCK_ACQUIRED,
                    operation=OperationKind.PUSH,
                    category=EventCategory.LIFECYCLE,
                    severity=EventSeverity.SUCCESS,
                    phase=EventPhase.EXECUTING,
                    correlation_id=correlation_id,
                ),
            )

            if not runtime_identity_matches(prepared.runtime_identity, scope.identity):
                emit_technical(
                    emitter,
                    build_technical_event(
                        event_id=EventId.PUSH_RUNTIME_CHANGED,
                        operation=OperationKind.PUSH,
                        category=EventCategory.SAFETY,
                        severity=EventSeverity.ERROR,
                        phase=EventPhase.EXECUTING,
                        correlation_id=correlation_id,
                        reason=runtime_changed_reason(),
                        outcome=OperationOutcome.STOPPED_SAFELY,
                    ),
                )
                return PushExecution(
                    prepared=prepared,
                    result=ExitCode.PUSH_ABORT,
                    outcome=OperationOutcome.STOPPED_SAFELY,
                    message=RUNTIME_CHANGED_MESSAGE,
                    target_updates=updates,
                    plan_identifier=preview.plan_identifier,
                    push_preview=preview,
                )

            conflict = _operation_deps.plan_fingerprint_conflict(prepared)
            if conflict is not None:
                emit_technical(
                    emitter,
                    build_technical_event(
                        event_id=EventId.PUSH_TARGET_CHANGED,
                        operation=OperationKind.PUSH,
                        category=EventCategory.SAFETY,
                        severity=EventSeverity.ERROR,
                        phase=EventPhase.EXECUTING,
                        correlation_id=correlation_id,
                        target_id=conflict,
                        outcome=OperationOutcome.STOPPED_SAFELY,
                    ),
                )
                return PushExecution(
                    prepared=prepared,
                    result=ExitCode.PUSH_ABORT,
                    outcome=OperationOutcome.STOPPED_SAFELY,
                    message=(
                        "A target changed after the preview was created. "
                        "The conflicting file was not overwritten."
                    ),
                    conflict_target=conflict,
                    target_updates=updates,
                    plan_identifier=preview.plan_identifier,
                )

            emit_technical(
                emitter,
                build_technical_event(
                    event_id=EventId.PUSH_PLAN_VERIFIED,
                    operation=OperationKind.PUSH,
                    category=EventCategory.LIFECYCLE,
                    severity=EventSeverity.SUCCESS,
                    phase=EventPhase.EXECUTING,
                    correlation_id=correlation_id,
                ),
            )
            total = max(len(prepared.targets), 1)
            emit_technical(
                emitter,
                build_technical_event(
                    event_id=EventId.PUSH_SNAPSHOTS_STARTED,
                    operation=OperationKind.PUSH,
                    category=EventCategory.TRANSACTION,
                    severity=EventSeverity.INFO,
                    phase=EventPhase.EXECUTING,
                    correlation_id=correlation_id,
                    completed=0,
                    total=total,
                ),
            )
            if prepared.wordlist_needs_write:
                emit_technical(
                    emitter,
                    build_technical_event(
                        event_id=EventId.PUSH_WORDLIST_WRITE_STARTED,
                        operation=OperationKind.PUSH,
                        category=EventCategory.TRANSACTION,
                        severity=EventSeverity.INFO,
                        phase=EventPhase.EXECUTING,
                        correlation_id=correlation_id,
                    ),
                )
            for index, target in enumerate(prepared.targets, start=1):
                emit_technical(
                    emitter,
                    build_technical_event(
                        event_id=EventId.PUSH_TARGET_STARTED,
                        operation=OperationKind.PUSH,
                        category=EventCategory.TARGET,
                        severity=EventSeverity.INFO,
                        phase=EventPhase.EXECUTING,
                        correlation_id=correlation_id,
                        target_id=target.planned.dictionary.name,
                        completed=index,
                        total=total,
                    ),
                )

            result = _operation_deps.execute_prepared_push(
                prepared,
                execution_context=scope.context,
                dry_run=False,
                running_app_skip_reasons_fn=running_app_skip_reasons_for(scope.context.settings),
            )
            return self._finalize_push_preview_result(
                prepared,
                preview,
                result,
                updates=updates,
                emitter=emitter,
                correlation_id=correlation_id,
            )

    def _finalize_push_preview_result(
        self,
        prepared: PreparedPush,
        preview: PushPreview,
        result: PushResult | ExitCode | PushAbort,
        *,
        updates: tuple,
        emitter: EventEmitter,
        correlation_id: str,
    ) -> PushExecution:
        wordlist = Path(prepared.ctx.wordlist_str)
        if isinstance(result, PushAbort):
            emit_technical(
                emitter,
                build_technical_event(
                    event_id=EventId.PUSH_ROLLBACK_STARTED,
                    operation=OperationKind.PUSH,
                    category=EventCategory.TRANSACTION,
                    severity=EventSeverity.ERROR,
                    phase=EventPhase.ROLLING_BACK,
                    correlation_id=correlation_id,
                    reason=push_abort_reason_to_event_reason(result.reason),
                ),
            )
            recovery = result.reason == "rollback_incomplete"
            if not recovery:
                journal = _operation_deps.load_journal_result(wordlist)
                recovery = journal.status is JournalLoadStatus.VALID_IN_PROGRESS
            outcome = (
                OperationOutcome.RECOVERY_REQUIRED if recovery else OperationOutcome.STOPPED_SAFELY
            )
            emit_technical(
                emitter,
                build_technical_event(
                    event_id=(
                        EventId.PUSH_RECOVERY_REQUIRED if recovery else EventId.PUSH_STOPPED_SAFELY
                    ),
                    operation=OperationKind.PUSH,
                    category=EventCategory.SAFETY if recovery else EventCategory.TRANSACTION,
                    severity=EventSeverity.ERROR if recovery else EventSeverity.WARNING,
                    phase=EventPhase.ROLLING_BACK,
                    correlation_id=correlation_id,
                    reason=push_abort_reason_to_event_reason(result.reason) if recovery else None,
                    outcome=outcome,
                ),
            )
            return PushExecution(
                prepared=prepared,
                result=result.exit_code,
                outcome=outcome,
                message=result.message,
                warnings=preview.warnings,
                target_updates=updates,
                recovery_required=recovery,
                plan_identifier=preview.plan_identifier,
                push_preview=preview,
            )

        if isinstance(result, ExitCode):
            journal = _operation_deps.load_journal_result(wordlist)
            recovery = journal.status is JournalLoadStatus.VALID_IN_PROGRESS
            outcome = (
                OperationOutcome.RECOVERY_REQUIRED if recovery else OperationOutcome.STOPPED_SAFELY
            )
            emit_technical(
                emitter,
                build_technical_event(
                    event_id=(EventId.PUSH_RECOVERY_REQUIRED if recovery else EventId.PUSH_FAILED),
                    operation=OperationKind.PUSH,
                    category=EventCategory.SAFETY if recovery else EventCategory.TRANSACTION,
                    severity=EventSeverity.ERROR,
                    phase=EventPhase.EXECUTING,
                    correlation_id=correlation_id,
                    reason=EventReason.JOURNAL_INVALID if recovery else None,
                    outcome=outcome,
                ),
            )
            return PushExecution(
                prepared=prepared,
                result=result,
                outcome=outcome,
                message="Push aborted safely.",
                warnings=preview.warnings,
                target_updates=updates,
                recovery_required=recovery,
                plan_identifier=preview.plan_identifier,
                push_preview=preview,
            )

        warnings = list(preview.warnings)
        for name in result.skipped:
            reason = result.skipped_reasons.get(name, "skipped")
            warnings.append(f"{name}: {reason}")
        outcome = (
            OperationOutcome.COMPLETED_WITH_WARNINGS
            if result.skipped
            else OperationOutcome.COMPLETED
        )
        emit_technical(
            emitter,
            build_technical_event(
                event_id=EventId.PUSH_FINALIZING,
                operation=OperationKind.PUSH,
                category=EventCategory.TRANSACTION,
                severity=EventSeverity.SUCCESS,
                phase=EventPhase.FINALIZING,
                correlation_id=correlation_id,
            ),
        )
        emit_technical(
            emitter,
            build_technical_event(
                event_id=EventId.PUSH_COMPLETED,
                operation=OperationKind.PUSH,
                category=EventCategory.LIFECYCLE,
                severity=EventSeverity.SUCCESS,
                phase=EventPhase.COMPLETED,
                correlation_id=correlation_id,
                outcome=outcome,
            ),
        )
        written = ", ".join(result.written) if result.written else "none"
        actual_updates = build_push_target_updates(preview, result)
        return PushExecution(
            prepared=prepared,
            result=result,
            outcome=outcome,
            message=f"Updated targets: {written}",
            warnings=tuple(warnings),
            target_updates=actual_updates,
            plan_identifier=preview.plan_identifier,
            push_preview=preview,
        )
