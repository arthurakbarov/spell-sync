"""Application facade for CLI and TUI."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ..application.project_resolution import effective_push_strict, resolve_project_wordlist
from ..application.requests import (
    DoctorRequest,
    PrepareTargetSettingsUpdateRequest,
    PullRequest,
    PushRequest,
    RecoveryRequest,
    SetupRequest,
    StatusRequest,
    SupportReportRequest,
    TargetSettingsRequest,
)
from ..diagnostics.history_builder import HistoryBuildContext, build_history_record
from ..diagnostics.history_store import OperationHistoryStore
from ..diagnostics.paths import AppStatePaths, resolve_app_state_paths
from ..diagnostics.technical_logging import (
    configure_file_logging,
    get_spell_sync_logger,
    read_technical_log_tail,
)
from ..diagnostics.types import (
    HistoryClearResult,
    OperationHistorySnapshot,
    TechnicalLogSnapshot,
)
from ..exit_codes import ExitCode
from ..health.report import build_doctor_report
from ..health.types import DoctorReport
from ..mutation_guards import invalid_config_exit_from_scope
from ..operation_lock import read_active_operation_lock
from ..project_setup.discovery import SetupTargetDiscovery, discover_setup_targets
from ..project_setup.draft import SetupDraft
from ..project_setup.execute import ProjectSetupExecution, execute_project_setup
from ..project_setup.prepare import PreparedProjectSetup, prepare_project_setup
from ..project_setup.state import ProjectSetupState, inspect_project_setup, validate_setup_wordlist
from ..project_setup.target_settings import (
    PreparedTargetSettingsUpdate,
    TargetSettingsExecution,
    TargetSettingsSnapshot,
    execute_target_settings_update,
    load_target_settings_snapshot,
    prepare_target_settings_update,
)
from ..push_abort import PushAbort
from ..push_journal import (
    JournalLoadStatus,
    cleanup_after_successful_recovery,
    discard_completed_journal,
    file_content_hash,
    load_journal_result,
    recover_from_journal,
    safe_discard_journal_file,
)
from ..push_prepared import PreparedPush, execute_prepared_push, plan_fingerprint_conflict
from ..settings import config_blocks_mutating
from ..sync_models import DictionaryDiff, PushResult
from ..sync_run import SyncRun
from .builders import (
    build_dashboard_state,
    build_doctor_snapshot,
    build_pull_add_from_preview,
    build_pull_operation_report,
    build_pull_preview,
    build_push_operation_report,
    build_push_preview,
    build_recovery_operation_report,
    build_recovery_preview,
    build_setup_operation_report,
    build_status_detail_snapshot,
    build_target_settings_operation_report,
)
from .events import EventLevel, EventSink, OperationEvent, OperationKind
from .operation_explanations import build_push_target_updates
from .reports import (
    DashboardState,
    DoctorSnapshot,
    DoctorTargetsSnapshot,
    DoctorTargetView,
    OperationOutcome,
    OperationReport,
    PullExecution,
    PullPreview,
    PushExecution,
    PushPreview,
    RecoveryExecution,
    RecoveryOutcome,
    RecoveryPreview,
    RecoveryStatus,
    StatusDetailSnapshot,
    StatusSnapshot,
)
from .runtime_resolver import RuntimeResolver

_HISTORY_SAVE_WARNING = "Operation completed, but its history record could not be saved."


def _emit(
    sink: EventSink | None,
    event: OperationEvent,
) -> None:
    if sink is not None:
        sink(event)


def _running_app_skip_reasons_for(settings):
    from ..app_process_check import running_app_skip_reasons

    def _fn(dictionary_names):
        return running_app_skip_reasons(dictionary_names, settings=settings)

    return _fn


class SpellSyncService:
    """UI-neutral entry point for spell-sync operations."""

    def _effective_push_strict(self, request: PushRequest) -> bool:
        resolved = self._runtime.resolve_read(request.project)
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
        resolved = self._runtime.resolve_read(request.project, strict_push=strict)
        if not config_blocks_mutating(resolved.config_result):
            return None
        return invalid_config_exit_from_scope(
            command,
            resolved.config_result,
            json_output=request.json_output,
        )

    def __init__(
        self,
        *,
        state_paths: AppStatePaths | None = None,
        history_store: OperationHistoryStore | None = None,
        enable_file_logging: bool = True,
        runtime_resolver: RuntimeResolver | None = None,
    ) -> None:
        self._state_paths = state_paths or resolve_app_state_paths()
        self._history_store = history_store or OperationHistoryStore(self._state_paths)
        self._runtime = runtime_resolver or RuntimeResolver()
        if enable_file_logging:
            setup = configure_file_logging(self._state_paths)
            if not setup.ok:
                get_spell_sync_logger().warning(
                    "technical log unavailable",
                    extra={"reason_code": "log_setup_failed"},
                )

    @property
    def state_paths(self) -> AppStatePaths:
        return self._state_paths

    def load_operation_history(
        self,
        *,
        limit: int = 50,
        operation: OperationKind | None = None,
        outcome: OperationOutcome | None = None,
    ) -> OperationHistorySnapshot:
        result = self._history_store.read_recent(
            limit=limit,
            operation=operation,
            outcome=outcome,
        )
        return OperationHistorySnapshot(
            records=result.records,
            malformed_lines=result.malformed_lines,
            detail=result.detail,
        )

    def clear_operation_history(self) -> HistoryClearResult:
        return self._history_store.clear()

    def technical_log_path(self) -> Path:
        return self._state_paths.technical_log

    def read_technical_log_tail(
        self,
        *,
        max_lines: int = 200,
        max_bytes: int = 128 * 1024,
    ) -> TechnicalLogSnapshot:
        return read_technical_log_tail(
            self._state_paths,
            max_lines=max_lines,
            max_bytes=max_bytes,
        )

    def load_support_report(self, request: SupportReportRequest):
        from ..application.support_report import build_support_report

        resolved = self._runtime.resolve_read(request.project)
        run = SyncRun(context=resolved.context)
        return build_support_report(self, request, resolved=resolved, run=run)

    def _finalize_report(
        self,
        report: OperationReport,
        *,
        source: object | None = None,
        duration_ms: int = 0,
    ) -> OperationReport:
        record = build_history_record(
            report,
            context=HistoryBuildContext(duration_ms=duration_ms),
            source=source,
        )
        write_result = self._history_store.append(record)
        if write_result.ok:
            return report
        get_spell_sync_logger().warning(
            "history append failed",
            extra={
                "reason_code": "history_append_failed",
                "record_id": record.record_id,
                "operation": report.operation,
            },
        )
        warnings = report.warnings + (_HISTORY_SAVE_WARNING,)
        return replace(report, warnings=warnings)

    def load_status(self, request: StatusRequest) -> StatusSnapshot:
        run = self._runtime.sync_run(request.project)
        wordlist_error = run.check_wordlist()
        if wordlist_error is not None:
            return StatusSnapshot(
                wordlist_count=0,
                diffs=(),
                skipped_unreadable=run.skipped_unreadable_dictionary_names(),
                skipped_corrupt=run.skipped_corrupt_dictionary_names(),
                wordlist_error=wordlist_error,
            )
        words = run.load_wordlist()
        return StatusSnapshot(
            wordlist_count=len(words),
            diffs=tuple(run.status_diffs(verbose=request.include_word_diffs)),
            skipped_unreadable=run.skipped_unreadable_dictionary_names(),
            skipped_corrupt=run.skipped_corrupt_dictionary_names(),
            destructive_risk=run.destructive_push_risk(),
            empty_wordlist=not words,
        )

    def load_status_detail(self, request: StatusRequest) -> StatusDetailSnapshot:
        run = self._runtime.sync_run(request.project)
        return build_status_detail_snapshot(run)

    def load_dashboard(self, request: StatusRequest) -> DashboardState:
        wordlist = resolve_project_wordlist(request.project)
        validated = self._runtime.validated(request.project)
        snapshot = self.load_status(request)
        lock_info = read_active_operation_lock(wordlist)
        last_operation_summary = None
        history = self.load_operation_history(limit=1)
        if history.records:
            from .builders import format_dashboard_last_operation

            last_operation_summary = format_dashboard_last_operation(history.records[0])
        return build_dashboard_state(
            validated,
            snapshot,
            lock_info=lock_info,
            last_operation_summary=last_operation_summary,
        )

    def load_push_preview(self, request: PushRequest) -> PushPreview:
        strict = self._effective_push_strict(request)
        run = self._runtime.sync_run(request.project, strict_push=strict)
        wordlist_error = run.check_wordlist()
        if wordlist_error is not None:
            return build_push_preview(None, wordlist_error=wordlist_error)
        prepared = self._prepare_push_for_run(run)
        if isinstance(prepared, ExitCode):
            return build_push_preview(None, prepare_error=prepared)
        return build_push_preview(prepared)

    def load_doctor(self, request: DoctorRequest) -> DoctorSnapshot:
        try:
            run = self._runtime.sync_run(request.project)
            report = build_doctor_report(run)
            return build_doctor_snapshot(report)
        except Exception:
            return DoctorSnapshot(
                checks=(),
                has_errors=True,
                load_error="Doctor report could not be loaded.",
            )

    def load_doctor_report(self, request: DoctorRequest) -> DoctorReport:
        run = self._runtime.sync_run(request.project)
        return build_doctor_report(run)

    def load_doctor_targets(self, request: DoctorRequest) -> DoctorTargetsSnapshot:
        from ..dictionaries import DictionaryFormat
        from ..read_outcome import dictionary_read_result

        run = self._runtime.sync_run(request.project)
        targets: list[DoctorTargetView] = []
        for dictionary in run.dictionaries:
            status = dictionary_read_result(dictionary).status
            fmt = (
                dictionary.format.value
                if isinstance(dictionary.format, DictionaryFormat)
                else str(dictionary.format)
            )
            targets.append(
                DoctorTargetView(
                    name=dictionary.name,
                    path=dictionary.path,
                    format=fmt,
                    read_status=status.value,
                )
            )
        return DoctorTargetsSnapshot(
            wordlist_path=str(Path(run.wordlist_str)),
            targets=tuple(targets),
        )

    def load_push_removals(self, request: PushRequest) -> tuple[DictionaryDiff, ...]:
        strict = self._effective_push_strict(request)
        run = self._runtime.sync_run(request.project, strict_push=strict)
        return tuple(diff for diff in run.status_diffs(verbose=True) if diff.to_remove > 0)

    def load_push_plan(
        self,
        request: PushRequest,
        *,
        verbose: bool = False,
    ) -> tuple[PushPreview, tuple[DictionaryDiff, ...], PushResult | ExitCode]:
        strict = self._effective_push_strict(request)
        run = self._runtime.sync_run(request.project, strict_push=strict)
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
        strict = self._effective_push_strict(request)
        with self._runtime.mutation_scope(
            request.project,
            "push",
            strict_push=strict,
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
        run = self._runtime.sync_run(request.project)
        if request.add_from is not None:
            return build_pull_add_from_preview(run, request.add_from)
        return build_pull_preview(run)

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

        _emit(
            event_sink,
            OperationEvent(OperationKind.PULL, "validating", "Validating pull preview"),
        )
        with self._runtime.mutation_scope(
            request.project,
            "pull",
            json_output=request.json_output,
        ) as scope:
            if isinstance(scope, int):
                _emit(
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

            _emit(
                event_sink,
                OperationEvent(
                    OperationKind.PULL,
                    "acquiring_lock",
                    "Operation lock acquired",
                    level=EventLevel.SUCCESS,
                ),
            )
            run = SyncRun(context=scope.context)
            if Path(preview.wordlist_path).resolve() != Path(run.wordlist_str).resolve():
                _emit(
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

            _emit(
                event_sink,
                OperationEvent(
                    OperationKind.PULL,
                    "verifying_plan",
                    "Verifying prepared pull plan",
                    level=EventLevel.SUCCESS,
                ),
            )
            _emit(
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
                current = file_content_hash(Path(run.wordlist_str))
                conflict = (
                    preview.wordlist_fingerprint is not None
                    and current is not None
                    and current != preview.wordlist_fingerprint
                )
                _emit(
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

            _emit(
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
        _emit(
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
            _emit(
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
        conflict = plan_fingerprint_conflict(prepared)
        if conflict is not None:
            _emit(
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

        _emit(
            event_sink,
            OperationEvent(
                OperationKind.PUSH,
                "verifying_plan",
                "Prepared plan verified",
                level=EventLevel.SUCCESS,
            ),
        )
        _emit(
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
        _emit(
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
        _emit(
            event_sink,
            OperationEvent(OperationKind.PUSH, "validating", "Validating configuration"),
        )
        strict = self._effective_push_strict(request)
        with self._runtime.mutation_scope(
            request.project,
            "push",
            strict_push=strict,
            json_output=request.json_output,
        ) as scope:
            if isinstance(scope, int):
                _emit(
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

            _emit(
                event_sink,
                OperationEvent(
                    OperationKind.PUSH,
                    "acquiring_lock",
                    "Operation lock acquired",
                    level=EventLevel.SUCCESS,
                ),
            )

            conflict = plan_fingerprint_conflict(prepared)
            if conflict is not None:
                _emit(
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

            _emit(
                event_sink,
                OperationEvent(
                    OperationKind.PUSH,
                    "verifying_plan",
                    "Prepared plan verified",
                    level=EventLevel.SUCCESS,
                ),
            )
            total = max(len(prepared.targets), 1)
            _emit(
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
                _emit(
                    event_sink,
                    OperationEvent(
                        OperationKind.PUSH,
                        "writing_wordlist",
                        "Updating canonical wordlist",
                    ),
                )
            for index, target in enumerate(prepared.targets, start=1):
                _emit(
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

            result = execute_prepared_push(
                prepared,
                dry_run=False,
                running_app_skip_reasons_fn=_running_app_skip_reasons_for(prepared.ctx.settings),
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
            _emit(
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
                journal = load_journal_result(wordlist)
                recovery = journal.status is JournalLoadStatus.VALID_IN_PROGRESS
            outcome = (
                OperationOutcome.RECOVERY_REQUIRED if recovery else OperationOutcome.STOPPED_SAFELY
            )
            stage = "failed" if recovery else "completed"
            _emit(
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
            journal = load_journal_result(wordlist)
            recovery = journal.status is JournalLoadStatus.VALID_IN_PROGRESS
            outcome = (
                OperationOutcome.RECOVERY_REQUIRED if recovery else OperationOutcome.STOPPED_SAFELY
            )
            _emit(
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
        _emit(
            event_sink,
            OperationEvent(
                OperationKind.PUSH,
                "finalizing",
                "Finalizing transaction",
                level=EventLevel.SUCCESS,
            ),
        )
        _emit(
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

    def inspect_recovery(self, request: RecoveryRequest) -> RecoveryPreview:
        validated = self._runtime.validated(
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

        _emit(
            event_sink,
            OperationEvent(OperationKind.RECOVER, "validating_journal", "Validating journal"),
        )
        with self._runtime.mutation_scope(
            request.project,
            "recover",
            allow_unfinished_journal=True,
            json_output=request.json_output,
        ) as scope:
            if isinstance(scope, int):
                _emit(
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

            _emit(
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

            _emit(
                event_sink,
                OperationEvent(
                    OperationKind.RECOVER,
                    "validating_snapshots",
                    "Validating recovery snapshots",
                    level=EventLevel.SUCCESS,
                ),
            )
            _emit(
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
                _emit(
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

            result = recover_from_journal(journal, dry_run=dry_run)
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
                _emit(
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

            cleanup_result = cleanup_after_successful_recovery(journal)
            if not cleanup_result.ok:
                _emit(
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
            _emit(
                event_sink,
                OperationEvent(
                    OperationKind.RECOVER,
                    "cleaning_artifacts",
                    "Cleaning recovery artifacts",
                    level=EventLevel.SUCCESS,
                ),
            )
            _emit(
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
        with self._runtime.mutation_scope(
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
            discard_result = discard_completed_journal(wordlist)
            if not discard_result.ok:
                return RecoveryExecution(
                    preview=preview,
                    result=ExitCode.PUSH_ABORT,
                    outcome=RecoveryOutcome.FAILED,
                    message=discard_result.detail or "Cleanup could not remove recovery artifacts.",
                )
            _emit(
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
        with self._runtime.mutation_scope(
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
                journal_ok, detail = safe_discard_journal_file(wordlist)
                if not journal_ok:
                    return RecoveryExecution(
                        preview=preview,
                        result=ExitCode.PUSH_ABORT,
                        outcome=RecoveryOutcome.FAILED,
                        message=detail or "Discard could not remove recovery metadata.",
                    )
            else:
                discard_result = discard_completed_journal(wordlist)
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

    def inspect_project_setup(self, request: SetupRequest) -> ProjectSetupState:
        return inspect_project_setup(
            resolve_project_wordlist(request.project),
            allow_project_creation=request.allow_project_creation,
        )

    def discover_setup_targets(self, draft: SetupDraft) -> SetupTargetDiscovery:
        return discover_setup_targets(selected_targets=draft.selected_targets)

    def prepare_project_setup(self, draft: SetupDraft) -> PreparedProjectSetup:
        return prepare_project_setup(draft)

    def execute_project_setup(
        self,
        prepared: PreparedProjectSetup,
        *,
        confirmed_setup_id: str,
        event_sink: EventSink | None = None,
    ) -> ProjectSetupExecution:
        def _sink(stage: str, message: str) -> None:
            _emit(
                event_sink,
                OperationEvent(
                    OperationKind.SETUP,
                    stage,
                    message,
                    level=EventLevel.SUCCESS if stage == "completed" else EventLevel.INFO,
                ),
            )

        return execute_project_setup(
            prepared,
            confirmed_setup_id=confirmed_setup_id,
            event_sink=_sink if event_sink is not None else None,
        )

    def validate_setup_wordlist(self, raw_path: str) -> tuple[Path, str | None]:
        return validate_setup_wordlist(raw_path)

    def build_setup_report(
        self,
        execution: ProjectSetupExecution,
        *,
        duration_ms: int = 0,
    ) -> OperationReport:
        report = build_setup_operation_report(execution)
        return self._finalize_report(report, source=execution, duration_ms=duration_ms)

    def load_target_settings(self, request: TargetSettingsRequest) -> TargetSettingsSnapshot:
        return load_target_settings_snapshot(
            wordlist=resolve_project_wordlist(request.project),
        )

    def prepare_target_settings_update(
        self,
        request: PrepareTargetSettingsUpdateRequest,
    ) -> PreparedTargetSettingsUpdate:
        wordlist = resolve_project_wordlist(request.project)
        validated = self._runtime.validated(request.project)
        pending_recovery = validated.journal_result.status not in (
            JournalLoadStatus.ABSENT,
            JournalLoadStatus.VALID_COMPLETED,
        )
        return prepare_target_settings_update(
            wordlist=wordlist,
            selected_target_ids=request.selected_target_ids,
            pending_recovery=pending_recovery,
        )

    def execute_target_settings_update(
        self,
        prepared: PreparedTargetSettingsUpdate,
        *,
        confirmed_update_id: str,
        event_sink: EventSink | None = None,
    ) -> TargetSettingsExecution:
        def _sink(stage: str, message: str) -> None:
            _emit(
                event_sink,
                OperationEvent(
                    OperationKind.TARGETS,
                    stage,
                    message,
                    level=EventLevel.SUCCESS if stage == "completed" else EventLevel.INFO,
                ),
            )

        return execute_target_settings_update(
            prepared,
            confirmed_update_id=confirmed_update_id,
            event_sink=_sink if event_sink is not None else None,
        )

    def build_target_settings_report(
        self,
        execution: TargetSettingsExecution,
        *,
        duration_ms: int = 0,
    ) -> OperationReport:
        report = build_target_settings_operation_report(execution)
        return self._finalize_report(report, source=execution, duration_ms=duration_ms)

    def build_push_report(
        self,
        execution: PushExecution,
        *,
        duration_ms: int = 0,
    ) -> OperationReport:
        report = build_push_operation_report(execution)
        return self._finalize_report(report, source=execution, duration_ms=duration_ms)

    def build_pull_report(
        self,
        execution: PullExecution,
        *,
        duration_ms: int = 0,
    ) -> OperationReport:
        report = build_pull_operation_report(execution)
        return self._finalize_report(report, source=execution, duration_ms=duration_ms)

    def build_support_report(self, request: SupportReportRequest):
        from ..sync_run import SyncRun
        from .support_report import build_support_report as _build_support_report

        resolved = self._runtime.resolve_read(request.project)
        run = SyncRun(context=resolved.context)
        return _build_support_report(
            self,
            request,
            resolved=resolved,
            run=run,
        )

    def build_recovery_report(
        self,
        execution: RecoveryExecution,
        *,
        duration_ms: int = 0,
    ) -> OperationReport:
        report = build_recovery_operation_report(execution)
        return self._finalize_report(report, source=execution, duration_ms=duration_ms)
