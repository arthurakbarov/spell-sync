"""Application facade for CLI and TUI."""

from __future__ import annotations

from pathlib import Path

from .. import command_helpers
from ..cli_options import CliOptions
from ..config import push_strict_enabled
from ..exit_codes import ExitCode
from ..health.report import build_doctor_report
from ..operation_lock import read_active_operation_lock
from ..paths import resolve_wordlist_path
from ..push_abort import PushAbort
from ..push_journal import (
    JournalLoadStatus,
    cleanup_after_successful_recovery,
    discard_completed_journal,
    discard_journal,
    file_content_hash,
    load_journal_result,
    recover_from_journal,
)
from ..push_prepared import PreparedPush, execute_prepared_push, plan_fingerprint_conflict
from ..sync_models import PushResult
from ..sync_run import SyncRun
from ..validated_runtime import build_validated_runtime
from .builders import (
    build_dashboard_state,
    build_doctor_snapshot,
    build_pull_operation_report,
    build_pull_preview,
    build_push_operation_report,
    build_push_preview,
    build_recovery_operation_report,
    build_recovery_preview,
    build_status_detail_snapshot,
    build_target_updates_from_preview,
)
from .events import EventLevel, EventSink, OperationEvent, OperationKind
from .reports import (
    DashboardState,
    DoctorSnapshot,
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


def _emit(
    sink: EventSink | None,
    event: OperationEvent,
) -> None:
    if sink is not None:
        sink(event)


def _running_app_skip_reasons(dictionary_names) -> dict[str, str]:
    from ..app_process_check import running_app_skip_reasons

    return running_app_skip_reasons(dictionary_names)


class SpellSyncService:
    """UI-neutral entry point for spell-sync operations."""

    def load_status(self, opts: CliOptions) -> StatusSnapshot:
        run = command_helpers.sync_run_for(opts)
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
            diffs=tuple(run.status_diffs(verbose=opts.verbose)),
            skipped_unreadable=run.skipped_unreadable_dictionary_names(),
            skipped_corrupt=run.skipped_corrupt_dictionary_names(),
            destructive_risk=run.destructive_push_risk(),
            empty_wordlist=not words,
        )

    def load_status_detail(self, opts: CliOptions) -> StatusDetailSnapshot:
        run = command_helpers.sync_run_for(opts)
        return build_status_detail_snapshot(run)

    def load_dashboard(self, opts: CliOptions) -> DashboardState:
        wordlist = resolve_wordlist_path(opts.wordlist)
        validated = build_validated_runtime(wordlist)
        snapshot = self.load_status(opts)
        lock_info = read_active_operation_lock(wordlist)
        return build_dashboard_state(validated, snapshot, lock_info=lock_info)

    def load_push_preview(self, opts: CliOptions) -> PushPreview:
        strict = opts.strict or push_strict_enabled()
        run = command_helpers.sync_run_for(opts, strict_push=strict)
        wordlist_error = run.check_wordlist()
        if wordlist_error is not None:
            return build_push_preview(None, wordlist_error=wordlist_error)
        prepared = self.prepare_push(run, opts)
        if isinstance(prepared, ExitCode):
            return build_push_preview(None, prepare_error=prepared)
        return build_push_preview(prepared)

    def load_doctor(self, opts: CliOptions) -> DoctorSnapshot:
        try:
            run = command_helpers.sync_run_for(opts)
            report = build_doctor_report(run)
            return build_doctor_snapshot(report)
        except Exception:
            return DoctorSnapshot(
                checks=(),
                has_errors=True,
                load_error="Doctor report could not be loaded.",
            )

    def prepare_pull(self, opts: CliOptions) -> PullPreview:
        run = command_helpers.sync_run_for(opts)
        return build_pull_preview(run)

    def execute_pull(
        self,
        opts: CliOptions,
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
        with command_helpers.mutating_command_scope(opts, "pull") as scope:
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

    def prepare_push(
        self,
        run: SyncRun,
        opts: CliOptions,
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
        skip_names = command_helpers.push_skip_running_app_dicts(run, opts)
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

    def execute_push(
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

    def run_push(
        self,
        run: SyncRun,
        opts: CliOptions,
        prepared: PreparedPush,
        *,
        dry_run: bool,
        event_sink: EventSink | None = None,
    ) -> PushExecution:
        result = self.execute_push(
            run,
            prepared,
            dry_run=dry_run,
            event_sink=event_sink,
        )
        outcome = OperationOutcome.COMPLETED
        if isinstance(result, ExitCode):
            outcome = OperationOutcome.FAILED
        elif result.skipped:
            outcome = OperationOutcome.COMPLETED_WITH_WARNINGS
        return PushExecution(prepared=prepared, result=result, outcome=outcome)

    def execute_push_preview(
        self,
        opts: CliOptions,
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
            )
        if confirmed_plan_id != preview.plan_identifier:
            return PushExecution(
                prepared=prepared,
                result=ExitCode.PUSH_ABORT,
                outcome=OperationOutcome.FAILED,
                message="Push confirmation does not match the current preview.",
                plan_identifier=preview.plan_identifier,
            )

        updates = build_target_updates_from_preview(preview)
        _emit(
            event_sink,
            OperationEvent(OperationKind.PUSH, "validating", "Validating configuration"),
        )
        strict = opts.strict or push_strict_enabled()
        with command_helpers.mutating_command_scope(
            opts,
            "push",
            strict_push=strict,
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
                running_app_skip_reasons_fn=_running_app_skip_reasons,
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
        return PushExecution(
            prepared=prepared,
            result=result,
            outcome=outcome,
            message=f"Updated targets: {written}",
            warnings=tuple(warnings),
            target_updates=updates,
            plan_identifier=preview.plan_identifier,
        )

    def inspect_recovery(self, opts: CliOptions) -> RecoveryPreview:
        wordlist = resolve_wordlist_path(opts.wordlist)
        validated = build_validated_runtime(wordlist, validate_journal_wordlist=True)
        return build_recovery_preview(validated)

    def execute_recovery(
        self,
        opts: CliOptions,
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
        with command_helpers.mutating_command_scope(
            opts,
            "recover",
            allow_unfinished_journal=True,
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

            result = recover_from_journal(journal, dry_run=False)
            incomplete = bool(result.failed or result.conflicts)
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

            cleanup_after_successful_recovery(journal)
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
        opts: CliOptions,
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
        with command_helpers.mutating_command_scope(
            opts,
            "recover",
            allow_unfinished_journal=True,
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
            discard_completed_journal(wordlist)
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
        opts: CliOptions,
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
        with command_helpers.mutating_command_scope(
            opts,
            "recover",
            allow_unfinished_journal=True,
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
                discard_journal(wordlist)
            else:
                discard_completed_journal(wordlist)
            return RecoveryExecution(
                preview=preview,
                result=ExitCode.OK,
                outcome=RecoveryOutcome.DISCARDED,
                message="Recovery metadata discarded.",
            )

    def build_push_report(self, execution: PushExecution) -> OperationReport:
        return build_push_operation_report(execution)

    def build_pull_report(self, execution: PullExecution) -> OperationReport:
        return build_pull_operation_report(execution)

    def build_recovery_report(self, execution: RecoveryExecution) -> OperationReport:
        return build_recovery_operation_report(execution)
