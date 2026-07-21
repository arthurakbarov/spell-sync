"""Pull and Push synchronization orchestration."""

from __future__ import annotations

from pathlib import Path

from ...application.project_resolution import effective_push_strict
from ...exit_codes import ExitCode
from ...mutation_guards import invalid_config_exit_from_scope
from ...push_abort import PushAbort
from ...push_journal import JournalLoadStatus
from ...push_prepared import PreparedPush
from ...runtime_identity import RUNTIME_CHANGED_AFTER_PREVIEW
from ...settings import config_blocks_mutating
from ...sync_models import DictionaryDiff, PushResult
from ...sync_run import SyncRun
from .. import _operation_deps
from ..builders import build_pull_add_from_preview, build_push_preview
from ..events import EventLevel, EventSink, OperationEvent, OperationKind
from ..operation_explanations import build_push_target_updates
from ..reports import OperationOutcome, PullExecution, PullPreview, PushExecution, PushPreview
from ..requests import PullRequest, PushRequest, RecoveryRequest
from ._shared import (
    RUNTIME_CHANGED_MESSAGE,
    emit,
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
            result = self._execute_push_for_run(run, prepared, dry_run=True)
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
        if confirmed_plan_id != preview.plan_identifier:
            return PullExecution(
                preview=preview,
                result=ExitCode.PUSH_ABORT,
                outcome=OperationOutcome.FAILED,
                message="Pull confirmation does not match the current preview.",
            )
        if not preview.is_executable:
            return PullExecution(
                preview=preview,
                result=preview.wordlist_error or preview.prepare_error or ExitCode.PUSH_ABORT,
                outcome=OperationOutcome.FAILED,
                message="Pull preview is not executable.",
            )

        emit(
            event_sink,
            OperationEvent(OperationKind.PULL, "validating", "Validating pull preview"),
        )
        with self._ctx.runtime.mutation_scope(
            request.project,
            "pull",
            json_output=request.json_output,
        ) as scope:
            if isinstance(scope, int):
                emit(
                    event_sink,
                    OperationEvent(
                        OperationKind.PULL,
                        "failed",
                        "Pull blocked by lock, config, or recovery state",
                        level=EventLevel.ERROR,
                    ),
                )
                return PullExecution(
                    preview=preview,
                    result=ExitCode(scope),
                    outcome=OperationOutcome.FAILED,
                    message="Pull could not acquire a safe execution context.",
                )

            emit(
                event_sink,
                OperationEvent(
                    OperationKind.PULL,
                    "acquiring_lock",
                    "Operation lock acquired",
                    level=EventLevel.SUCCESS,
                ),
            )
            run = SyncRun(context=scope.context)
            if preview.runtime_identity is not None and not runtime_identity_matches(
                preview.runtime_identity, scope.identity
            ):
                emit(
                    event_sink,
                    OperationEvent(
                        OperationKind.PULL,
                        "verifying_plan",
                        RUNTIME_CHANGED_AFTER_PREVIEW,
                        level=EventLevel.ERROR,
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
                emit(
                    event_sink,
                    OperationEvent(
                        OperationKind.PULL,
                        "failed",
                        "Preview wordlist path mismatch",
                        level=EventLevel.ERROR,
                    ),
                )
                return PullExecution(
                    preview=preview,
                    result=ExitCode.PUSH_ABORT,
                    outcome=OperationOutcome.FAILED,
                    message="Pull preview does not match the active wordlist.",
                )

            emit(
                event_sink,
                OperationEvent(
                    OperationKind.PULL,
                    "verifying_plan",
                    "Verifying prepared pull plan",
                    level=EventLevel.SUCCESS,
                ),
            )
            emit(
                event_sink,
                OperationEvent(
                    OperationKind.PULL,
                    "writing_wordlist",
                    "Writing canonical wordlist",
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
                emit(
                    event_sink,
                    OperationEvent(
                        OperationKind.PULL,
                        "failed",
                        "Wordlist changed after preview" if conflict else "Pull write failed",
                        level=EventLevel.ERROR,
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

            emit(
                event_sink,
                OperationEvent(
                    OperationKind.PULL,
                    "completed",
                    "Pull completed",
                    level=EventLevel.SUCCESS,
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
    ) -> PreparedPush | ExitCode:
        emit(
            event_sink,
            OperationEvent(
                OperationKind.PUSH,
                "building_plan",
                "Building push plan",
            ),
        )
        skip_names: frozenset[str] = frozenset()
        prepared = run.prepare_push_operation(skip_names=skip_names)
        if isinstance(prepared, ExitCode):
            emit(
                event_sink,
                OperationEvent(
                    OperationKind.PUSH,
                    "building_plan",
                    "Push plan failed",
                    level=EventLevel.ERROR,
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
    ) -> PushResult | ExitCode:
        conflict = _operation_deps.plan_fingerprint_conflict(prepared)
        if conflict is not None:
            emit(
                event_sink,
                OperationEvent(
                    OperationKind.PUSH,
                    "verifying_plan",
                    f"{conflict} changed after plan",
                    level=EventLevel.ERROR,
                    target=conflict,
                ),
            )
            return ExitCode.PUSH_ABORT

        emit(
            event_sink,
            OperationEvent(
                OperationKind.PUSH,
                "verifying_plan",
                "Prepared plan verified",
                level=EventLevel.SUCCESS,
            ),
        )
        emit(
            event_sink,
            OperationEvent(
                OperationKind.PUSH,
                "creating_snapshots" if not dry_run else "dry_run",
                "Starting push execution",
            ),
        )
        if dry_run:
            result = run._run_push_transaction(dry_run=True, prepared=prepared)
        else:
            result = run.push_from_wordlist(prepared=prepared)
        level = EventLevel.SUCCESS if isinstance(result, PushResult) else EventLevel.ERROR
        stage = "completed" if isinstance(result, PushResult) else "failed"
        emit(
            event_sink,
            OperationEvent(
                OperationKind.PUSH,
                stage,
                "Push execution finished",
                level=level,
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
    ) -> PushExecution:
        result = self._execute_push_for_run(
            run,
            prepared,
            dry_run=dry_run,
            event_sink=event_sink,
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
        emit(
            event_sink,
            OperationEvent(OperationKind.PUSH, "validating", "Validating configuration"),
        )
        strict_override = request.strict_override
        with self._ctx.runtime.mutation_scope(
            request.project,
            "push",
            strict_push_override=strict_override,
            json_output=request.json_output,
        ) as scope:
            if isinstance(scope, int):
                emit(
                    event_sink,
                    OperationEvent(
                        OperationKind.PUSH,
                        "failed",
                        "Push blocked by lock, config, or recovery state",
                        level=EventLevel.ERROR,
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

            emit(
                event_sink,
                OperationEvent(
                    OperationKind.PUSH,
                    "acquiring_lock",
                    "Operation lock acquired",
                    level=EventLevel.SUCCESS,
                ),
            )

            if not runtime_identity_matches(prepared.runtime_identity, scope.identity):
                emit(
                    event_sink,
                    OperationEvent(
                        OperationKind.PUSH,
                        "verifying_plan",
                        RUNTIME_CHANGED_AFTER_PREVIEW,
                        level=EventLevel.ERROR,
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
                emit(
                    event_sink,
                    OperationEvent(
                        OperationKind.PUSH,
                        "verifying_plan",
                        f"{conflict} changed after preview",
                        level=EventLevel.ERROR,
                        target=conflict,
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

            emit(
                event_sink,
                OperationEvent(
                    OperationKind.PUSH,
                    "verifying_plan",
                    "Prepared plan verified",
                    level=EventLevel.SUCCESS,
                ),
            )
            total = max(len(prepared.targets), 1)
            emit(
                event_sink,
                OperationEvent(
                    OperationKind.PUSH,
                    "creating_snapshots",
                    "Creating recovery snapshots",
                    completed=0,
                    total=total,
                ),
            )
            if prepared.wordlist_needs_write:
                emit(
                    event_sink,
                    OperationEvent(
                        OperationKind.PUSH,
                        "writing_wordlist",
                        "Updating canonical wordlist",
                    ),
                )
            for index, target in enumerate(prepared.targets, start=1):
                emit(
                    event_sink,
                    OperationEvent(
                        OperationKind.PUSH,
                        "writing_target",
                        f"Updating {target.planned.dictionary.name}",
                        target=target.planned.dictionary.name,
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
                event_sink=event_sink,
            )

    def _finalize_push_preview_result(
        self,
        prepared: PreparedPush,
        preview: PushPreview,
        result: PushResult | ExitCode | PushAbort,
        *,
        updates: tuple,
        event_sink: EventSink | None,
    ) -> PushExecution:
        wordlist = Path(prepared.ctx.wordlist_str)
        if isinstance(result, PushAbort):
            emit(
                event_sink,
                OperationEvent(
                    OperationKind.PUSH,
                    "rolling_back",
                    result.message,
                    level=EventLevel.ERROR,
                ),
            )
            recovery = result.reason == "rollback_incomplete"
            if not recovery:
                journal = _operation_deps.load_journal_result(wordlist)
                recovery = journal.status is JournalLoadStatus.VALID_IN_PROGRESS
            outcome = (
                OperationOutcome.RECOVERY_REQUIRED if recovery else OperationOutcome.STOPPED_SAFELY
            )
            stage = "failed" if recovery else "completed"
            emit(
                event_sink,
                OperationEvent(
                    OperationKind.PUSH,
                    stage,
                    "Push stopped after rollback handling",
                    level=EventLevel.ERROR if recovery else EventLevel.WARNING,
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
            emit(
                event_sink,
                OperationEvent(
                    OperationKind.PUSH,
                    "failed",
                    "Push aborted",
                    level=EventLevel.ERROR,
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
        emit(
            event_sink,
            OperationEvent(
                OperationKind.PUSH,
                "finalizing",
                "Finalizing transaction",
                level=EventLevel.SUCCESS,
            ),
        )
        emit(
            event_sink,
            OperationEvent(
                OperationKind.PUSH,
                "completed",
                "Push completed",
                level=EventLevel.SUCCESS,
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
