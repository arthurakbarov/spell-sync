"""Application facade for CLI and TUI."""

from __future__ import annotations

from .. import command_helpers
from ..cli_options import CliOptions
from ..exit_codes import ExitCode
from ..health.report import build_doctor_report
from ..operation_lock import read_active_operation_lock
from ..paths import resolve_wordlist_path
from ..push_prepared import PreparedPush, plan_fingerprint_conflict
from ..sync_run import PushResult, SyncRun
from ..validated_runtime import build_validated_runtime
from .builders import (
    build_dashboard_state,
    build_doctor_snapshot,
    build_push_preview,
    build_status_detail_snapshot,
)
from .events import EventLevel, EventSink, OperationEvent, OperationKind
from .reports import (
    DashboardState,
    DoctorSnapshot,
    PushExecution,
    PushPreview,
    StatusDetailSnapshot,
    StatusSnapshot,
)


def _emit(
    sink: EventSink | None,
    event: OperationEvent,
) -> None:
    if sink is not None:
        sink(event)


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
        from ..config import push_strict_enabled

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
                    "plan_verified",
                    f"{conflict} changed after plan",
                    level=EventLevel.ERROR,
                ),
            )
            return ExitCode.PUSH_ABORT

        _emit(
            event_sink,
            OperationEvent(
                OperationKind.PUSH,
                "plan_verified",
                "Prepared plan verified",
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
        _emit(
            event_sink,
            OperationEvent(
                OperationKind.PUSH,
                "completed",
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
        return PushExecution(prepared=prepared, result=result)
