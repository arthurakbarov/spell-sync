"""Application facade for CLI and TUI."""

from __future__ import annotations

from pathlib import Path

from ..diagnostics.history_store import OperationHistoryStore
from ..diagnostics.paths import AppStatePaths, resolve_app_state_paths
from ..diagnostics.technical_logging import configure_file_logging, get_spell_sync_logger
from ..diagnostics.types import HistoryClearResult, OperationHistorySnapshot, TechnicalLogSnapshot
from ..exit_codes import ExitCode
from ..health.types import DoctorReport
from ..project_setup.discovery import SetupTargetDiscovery
from ..project_setup.draft import SetupDraft
from ..project_setup.execute import ProjectSetupExecution
from ..project_setup.prepare import PreparedProjectSetup
from ..project_setup.state import ProjectSetupState
from ..project_setup.target_settings import (
    PreparedTargetSettingsUpdate,
    TargetSettingsExecution,
    TargetSettingsSnapshot,
)
from ..push_prepared import PreparedPush
from ..sync_models import DictionaryDiff, PushResult
from ..sync_run import SyncRun
from ._operation_deps import (  # noqa: F401 — legacy test patch surface
    build_doctor_report,
    build_doctor_snapshot,
    build_pull_preview,
    build_status_detail_snapshot,
    cleanup_after_successful_recovery,
    discard_completed_journal,
    execute_prepared_push,
    file_content_hash,
    load_journal_result,
    plan_fingerprint_conflict,
    read_active_operation_lock,
    recover_from_journal,
    safe_discard_journal_file,
)
from .events import EventSink, OperationKind
from .reports import (
    DashboardState,
    DoctorSnapshot,
    DoctorTargetsSnapshot,
    OperationOutcome,
    OperationReport,
    PullExecution,
    PullPreview,
    PushExecution,
    PushPreview,
    RecoveryExecution,
    RecoveryPreview,
    StatusDetailSnapshot,
    StatusSnapshot,
)
from .requests import (
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
from .runtime_resolver import RuntimeResolver
from .services import (
    ApplicationContext,
    DiagnosticsService,
    InspectionService,
    RecoveryService,
    SetupService,
    SyncService,
    TargetSettingsService,
)


class SpellSyncService:
    """UI-neutral entry point for spell-sync operations."""

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
        self._ctx = ApplicationContext(
            runtime=self._runtime,
            history_store=self._history_store,
            state_paths=self._state_paths,
        )
        self._diagnostics = DiagnosticsService(self._ctx)
        self._inspection = InspectionService(self._ctx, self._diagnostics)
        self._sync = SyncService(self._ctx)
        self._recovery = RecoveryService(self._ctx)
        self._setup = SetupService(self._ctx)
        self._target_settings = TargetSettingsService(self._ctx)
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

    def mutating_config_exit_code(
        self,
        request: PullRequest | PushRequest | RecoveryRequest,
        command: str,
    ) -> int | None:
        return self._sync.mutating_config_exit_code(request, command)

    def load_operation_history(
        self,
        *,
        limit: int = 50,
        operation: OperationKind | None = None,
        outcome: OperationOutcome | None = None,
    ) -> OperationHistorySnapshot:
        return self._diagnostics.load_operation_history(
            limit=limit,
            operation=operation,
            outcome=outcome,
        )

    def clear_operation_history(self) -> HistoryClearResult:
        return self._diagnostics.clear_operation_history()

    def technical_log_path(self) -> Path:
        return self._diagnostics.technical_log_path()

    def read_technical_log_tail(
        self,
        *,
        max_lines: int = 200,
        max_bytes: int = 128 * 1024,
    ) -> TechnicalLogSnapshot:
        return self._diagnostics.read_technical_log_tail(
            max_lines=max_lines,
            max_bytes=max_bytes,
        )

    def load_support_report(self, request: SupportReportRequest):
        return self._diagnostics.load_support_report(request)

    def load_status(self, request: StatusRequest) -> StatusSnapshot:
        return self._inspection.load_status(request)

    def load_status_detail(self, request: StatusRequest) -> StatusDetailSnapshot:
        return self._inspection.load_status_detail(request)

    def load_dashboard(self, request: StatusRequest) -> DashboardState:
        return self._inspection.load_dashboard(request)

    def load_push_preview(self, request: PushRequest) -> PushPreview:
        return self._sync.load_push_preview(request)

    def load_doctor(self, request: DoctorRequest) -> DoctorSnapshot:
        return self._inspection.load_doctor(request)

    def load_doctor_report(self, request: DoctorRequest) -> DoctorReport:
        return self._inspection.load_doctor_report(request)

    def load_doctor_targets(self, request: DoctorRequest) -> DoctorTargetsSnapshot:
        return self._inspection.load_doctor_targets(request)

    def load_push_removals(self, request: PushRequest) -> tuple[DictionaryDiff, ...]:
        return self._sync.load_push_removals(request)

    def load_push_plan(
        self,
        request: PushRequest,
        *,
        verbose: bool = False,
    ) -> tuple[PushPreview, tuple[DictionaryDiff, ...], PushResult | ExitCode]:
        return self._sync.load_push_plan(request, verbose=verbose)

    def execute_push_dry_run(self, request: PushRequest, preview: PushPreview) -> PushExecution:
        return self._sync.execute_push_dry_run(request, preview)

    def prepare_pull(self, request: PullRequest) -> PullPreview:
        return self._sync.prepare_pull(request)

    def execute_pull(
        self,
        request: PullRequest,
        preview: PullPreview,
        *,
        confirmed_plan_id: str,
        event_sink: EventSink | None = None,
    ) -> PullExecution:
        return self._sync.execute_pull(
            request,
            preview,
            confirmed_plan_id=confirmed_plan_id,
            event_sink=event_sink,
        )

    def pull_execution_from_result(
        self,
        preview: PullPreview,
        result: tuple[int, int] | ExitCode,
    ) -> PullExecution:
        return self._sync.pull_execution_from_result(preview, result)

    def push_execution_from_result(
        self,
        prepared: PreparedPush,
        result: PushResult | ExitCode,
    ) -> PushExecution:
        return self._sync.push_execution_from_result(prepared, result)

    def execute_push_preview(
        self,
        request: PushRequest,
        preview: PushPreview,
        *,
        confirmed_plan_id: str,
        event_sink: EventSink | None = None,
    ) -> PushExecution:
        return self._sync.execute_push_preview(
            request,
            preview,
            confirmed_plan_id=confirmed_plan_id,
            event_sink=event_sink,
        )

    def inspect_recovery(self, request: RecoveryRequest) -> RecoveryPreview:
        return self._recovery.inspect_recovery(request)

    def execute_recovery(
        self,
        request: RecoveryRequest,
        preview: RecoveryPreview,
        *,
        confirmed_transaction_id: str,
        dry_run: bool = False,
        event_sink: EventSink | None = None,
    ) -> RecoveryExecution:
        return self._recovery.execute_recovery(
            request,
            preview,
            confirmed_transaction_id=confirmed_transaction_id,
            dry_run=dry_run,
            event_sink=event_sink,
        )

    def execute_recovery_cleanup(
        self,
        request: RecoveryRequest,
        preview: RecoveryPreview,
        *,
        confirmed_transaction_id: str,
        event_sink: EventSink | None = None,
    ) -> RecoveryExecution:
        return self._recovery.execute_recovery_cleanup(
            request,
            preview,
            confirmed_transaction_id=confirmed_transaction_id,
            event_sink=event_sink,
        )

    def execute_recovery_discard(
        self,
        request: RecoveryRequest,
        preview: RecoveryPreview,
        *,
        confirmed_transaction_id: str,
        event_sink: EventSink | None = None,
    ) -> RecoveryExecution:
        return self._recovery.execute_recovery_discard(
            request,
            preview,
            confirmed_transaction_id=confirmed_transaction_id,
            event_sink=event_sink,
        )

    def inspect_project_setup(self, request: SetupRequest) -> ProjectSetupState:
        return self._setup.inspect_project_setup(request)

    def discover_setup_targets(self, draft: SetupDraft) -> SetupTargetDiscovery:
        return self._setup.discover_setup_targets(draft)

    def prepare_project_setup(self, draft: SetupDraft) -> PreparedProjectSetup:
        return self._setup.prepare_project_setup(draft)

    def execute_project_setup(
        self,
        prepared: PreparedProjectSetup,
        *,
        confirmed_setup_id: str,
        event_sink: EventSink | None = None,
    ) -> ProjectSetupExecution:
        return self._setup.execute_project_setup(
            prepared,
            confirmed_setup_id=confirmed_setup_id,
            event_sink=event_sink,
        )

    def validate_setup_wordlist(self, raw_path: str) -> tuple[Path, str | None]:
        return self._setup.validate_setup_wordlist(raw_path)

    def build_setup_report(
        self,
        execution: ProjectSetupExecution,
        *,
        duration_ms: int = 0,
    ) -> OperationReport:
        return self._diagnostics.build_setup_report(execution, duration_ms=duration_ms)

    def load_target_settings(self, request: TargetSettingsRequest) -> TargetSettingsSnapshot:
        return self._target_settings.load_target_settings(request)

    def prepare_target_settings_update(
        self,
        request: PrepareTargetSettingsUpdateRequest,
    ) -> PreparedTargetSettingsUpdate:
        return self._target_settings.prepare_target_settings_update(request)

    def execute_target_settings_update(
        self,
        prepared: PreparedTargetSettingsUpdate,
        *,
        confirmed_update_id: str,
        event_sink: EventSink | None = None,
    ) -> TargetSettingsExecution:
        return self._target_settings.execute_target_settings_update(
            prepared,
            confirmed_update_id=confirmed_update_id,
            event_sink=event_sink,
        )

    def build_target_settings_report(
        self,
        execution: TargetSettingsExecution,
        *,
        duration_ms: int = 0,
    ) -> OperationReport:
        return self._diagnostics.build_target_settings_report(execution, duration_ms=duration_ms)

    def build_push_report(
        self,
        execution: PushExecution,
        *,
        duration_ms: int = 0,
    ) -> OperationReport:
        return self._diagnostics.build_push_report(execution, duration_ms=duration_ms)

    def build_pull_report(
        self,
        execution: PullExecution,
        *,
        duration_ms: int = 0,
    ) -> OperationReport:
        return self._diagnostics.build_pull_report(execution, duration_ms=duration_ms)

    def build_support_report(self, request: SupportReportRequest):
        return self._diagnostics.build_support_report(request)

    def build_recovery_report(
        self,
        execution: RecoveryExecution,
        *,
        duration_ms: int = 0,
    ) -> OperationReport:
        return self._diagnostics.build_recovery_report(execution, duration_ms=duration_ms)

    def _finalize_report(
        self,
        report: OperationReport,
        *,
        source: object | None = None,
        duration_ms: int = 0,
    ) -> OperationReport:
        return self._diagnostics.finalize_report(
            report,
            source=source,
            duration_ms=duration_ms,
        )

    def _prepare_push_for_run(
        self,
        run: SyncRun,
        *,
        event_sink: EventSink | None = None,
    ) -> PreparedPush | ExitCode:
        return self._sync._prepare_push_for_run(run, event_sink=event_sink)

    def _execute_push_for_run(
        self,
        run: SyncRun,
        prepared: PreparedPush,
        *,
        dry_run: bool,
        event_sink: EventSink | None = None,
    ) -> PushResult | ExitCode:
        return self._sync._execute_push_for_run(
            run,
            prepared,
            dry_run=dry_run,
            event_sink=event_sink,
        )

    def _run_push_for_run(
        self,
        run: SyncRun,
        prepared: PreparedPush,
        *,
        dry_run: bool,
        event_sink: EventSink | None = None,
    ) -> PushExecution:
        return self._sync._run_push_for_run(
            run,
            prepared,
            dry_run=dry_run,
            event_sink=event_sink,
        )
