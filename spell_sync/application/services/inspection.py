"""Read-only inspection: status, dashboard, and doctor."""

from __future__ import annotations

from pathlib import Path

from ...application.project_resolution import resolve_project_wordlist
from ...health.types import DoctorReport
from .. import _operation_deps
from ..builders import build_dashboard_state
from ..reports import (
    DashboardState,
    DoctorSnapshot,
    DoctorTargetsSnapshot,
    DoctorTargetView,
    StatusDetailSnapshot,
    StatusSnapshot,
)
from ..requests import DoctorRequest, StatusRequest
from .context import ApplicationContext
from .diagnostics import DiagnosticsService


class InspectionService:
    def __init__(self, ctx: ApplicationContext, diagnostics: DiagnosticsService) -> None:
        self._ctx = ctx
        self._diagnostics = diagnostics

    def load_status(self, request: StatusRequest) -> StatusSnapshot:
        run = self._ctx.runtime.sync_run(request.project)
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
        run = self._ctx.runtime.sync_run(request.project)
        return _operation_deps.build_status_detail_snapshot(run)

    def load_dashboard(self, request: StatusRequest) -> DashboardState:
        wordlist = resolve_project_wordlist(request.project)
        validated = self._ctx.runtime.validated(request.project)
        snapshot = self.load_status(request)
        lock_info = _operation_deps.read_active_operation_lock(wordlist)
        last_operation_summary = None
        history = self._diagnostics.load_operation_history(limit=1)
        if history.records:
            from ..builders import format_dashboard_last_operation

            last_operation_summary = format_dashboard_last_operation(history.records[0])
        return build_dashboard_state(
            validated,
            snapshot,
            lock_info=lock_info,
            last_operation_summary=last_operation_summary,
        )

    def load_doctor(self, request: DoctorRequest) -> DoctorSnapshot:
        try:
            run = self._ctx.runtime.sync_run(request.project)
            report = _operation_deps.build_doctor_report(run)
            return _operation_deps.build_doctor_snapshot(report)
        except Exception:
            return DoctorSnapshot(
                checks=(),
                has_errors=True,
                load_error="Doctor report could not be loaded.",
            )

    def load_doctor_report(self, request: DoctorRequest) -> DoctorReport:
        run = self._ctx.runtime.sync_run(request.project)
        return _operation_deps.build_doctor_report(run)

    def load_doctor_targets(self, request: DoctorRequest) -> DoctorTargetsSnapshot:
        from ...dictionaries import DictionaryFormat
        from ...read_outcome import dictionary_read_result

        run = self._ctx.runtime.sync_run(request.project)
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
