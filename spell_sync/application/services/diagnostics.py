"""Operation history, technical log, and report finalization."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ...diagnostics.history_builder import HistoryBuildContext, build_history_record
from ...diagnostics.technical_logging import get_spell_sync_logger, read_technical_log_tail
from ...diagnostics.types import HistoryClearResult, OperationHistorySnapshot, TechnicalLogSnapshot
from ...project_setup.execute import ProjectSetupExecution
from ...project_setup.target_settings import TargetSettingsExecution
from ...sync_run import SyncRun
from ..builders import (
    build_pull_operation_report,
    build_push_operation_report,
    build_recovery_operation_report,
    build_setup_operation_report,
    build_target_settings_operation_report,
)
from ..events import OperationKind
from ..reports import (
    OperationOutcome,
    OperationReport,
    PullExecution,
    PushExecution,
    RecoveryExecution,
)
from ..requests import SupportReportRequest
from ._shared import HISTORY_SAVE_WARNING
from .context import ApplicationContext


class DiagnosticsService:
    def __init__(self, ctx: ApplicationContext) -> None:
        self._ctx = ctx

    def load_operation_history(
        self,
        *,
        limit: int = 50,
        operation: OperationKind | None = None,
        outcome: OperationOutcome | None = None,
    ) -> OperationHistorySnapshot:
        result = self._ctx.history_store.read_recent(
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
        return self._ctx.history_store.clear()

    def technical_log_path(self) -> Path:
        return self._ctx.state_paths.technical_log

    def read_technical_log_tail(
        self,
        *,
        max_lines: int = 200,
        max_bytes: int = 128 * 1024,
    ) -> TechnicalLogSnapshot:
        return read_technical_log_tail(
            self._ctx.state_paths,
            max_lines=max_lines,
            max_bytes=max_bytes,
        )

    def load_support_report(self, request: SupportReportRequest):
        from ..support_report import build_support_report

        resolved = self._ctx.runtime.resolve_read(request.project)
        run = SyncRun(context=resolved.context)
        return build_support_report(self, request, resolved=resolved, run=run)

    def finalize_report(
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
        write_result = self._ctx.history_store.append(record)
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
        warnings = report.warnings + (HISTORY_SAVE_WARNING,)
        return replace(report, warnings=warnings)

    def build_setup_report(
        self,
        execution: ProjectSetupExecution,
        *,
        duration_ms: int = 0,
    ) -> OperationReport:
        report = build_setup_operation_report(execution)
        return self.finalize_report(report, source=execution, duration_ms=duration_ms)

    def build_target_settings_report(
        self,
        execution: TargetSettingsExecution,
        *,
        duration_ms: int = 0,
    ) -> OperationReport:
        report = build_target_settings_operation_report(execution)
        return self.finalize_report(report, source=execution, duration_ms=duration_ms)

    def build_push_report(
        self,
        execution: PushExecution,
        *,
        duration_ms: int = 0,
    ) -> OperationReport:
        report = build_push_operation_report(execution)
        return self.finalize_report(report, source=execution, duration_ms=duration_ms)

    def build_pull_report(
        self,
        execution: PullExecution,
        *,
        duration_ms: int = 0,
    ) -> OperationReport:
        report = build_pull_operation_report(execution)
        return self.finalize_report(report, source=execution, duration_ms=duration_ms)

    def build_support_report(self, request: SupportReportRequest):
        from ..sync_run import SyncRun
        from .support_report import build_support_report as _build_support_report

        resolved = self._ctx.runtime.resolve_read(request.project)
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
        return self.finalize_report(report, source=execution, duration_ms=duration_ms)
