"""Read-only inspection: status, dashboard, and doctor."""

from pathlib import Path

from ...dictionary_hints import project_honesty_warnings
from ...health.types import DoctorReport
from ...sync_run import SyncRun, sync_run_for
from .. import _operation_deps
from ..dashboard_builders import build_dashboard_state
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

    def load_status(
        self,
        request: StatusRequest,
        *,
        run: SyncRun | None = None,
    ) -> StatusSnapshot:
        sync = run if run is not None else self._ctx.runtime.sync_run(request.project)
        wordlist_error = sync.check_wordlist()
        if wordlist_error is not None:
            return StatusSnapshot(
                wordlist_count=0,
                diffs=(),
                skipped_unreadable=sync.skipped_unreadable_dictionary_names(),
                skipped_corrupt=sync.skipped_corrupt_dictionary_names(),
                wordlist_error=wordlist_error,
            )
        words = sync.load_wordlist()
        return StatusSnapshot(
            wordlist_count=len(words),
            diffs=tuple(sync.status_diffs(verbose=request.include_word_diffs)),
            skipped_unreadable=sync.skipped_unreadable_dictionary_names(),
            skipped_corrupt=sync.skipped_corrupt_dictionary_names(),
            destructive_risk=sync.destructive_push_risk(),
            empty_wordlist=not words,
            honesty_warnings=tuple(
                project_honesty_warnings(
                    Path(sync.wordlist_str),
                    settings=sync.context.settings,
                )
            ),
        )

    def load_status_detail(self, request: StatusRequest) -> StatusDetailSnapshot:
        run = self._ctx.runtime.sync_run(request.project)
        return _operation_deps.build_status_detail_snapshot(run)

    def load_dashboard(self, request: StatusRequest) -> DashboardState:
        validated = self._ctx.runtime.validated(request.project)
        snapshot = self.load_status(request, run=sync_run_for(validated))
        lock_info = _operation_deps.read_active_operation_lock(validated.context.wordlist)
        last_operation_summary = None
        history = self._diagnostics.load_operation_history(limit=1)
        if history.records:
            from ..dashboard_builders import format_dashboard_last_operation

            last_operation_summary = format_dashboard_last_operation(history.records[0])
        return build_dashboard_state(
            validated,
            snapshot,
            lock_info=lock_info,
            last_operation_summary=last_operation_summary,
        )

    def load_doctor(self, request: DoctorRequest) -> DoctorSnapshot:
        from importlib.metadata import PackageNotFoundError

        from ...diagnostics.debug_mode import (
            emit_boundary_technical_event,
            emit_debug_traceback,
        )
        from ...diagnostics.technical_event_model import EventId, OperationKind
        from ...resolved_runtime import ProjectRuntimeMismatchError

        # Expected from sync_run → build_doctor_report → build_doctor_snapshot:
        # filesystem/config I/O, decode failures, missing package metadata, identity mismatch.
        # Programming errors (TypeError/KeyError/AssertionError/...) are unexpected.
        expected = (
            OSError,
            UnicodeError,
            PackageNotFoundError,
            ProjectRuntimeMismatchError,
        )
        try:
            run = self._ctx.runtime.sync_run(request.project)
            report = _operation_deps.build_doctor_report(run)
            return _operation_deps.build_doctor_snapshot(report)
        except expected:
            return DoctorSnapshot.unavailable()
        except Exception as exc:
            emit_debug_traceback(exc)
            emit_boundary_technical_event(
                EventId.DIAGNOSTICS_DOCTOR_UNEXPECTED_FAILURE,
                operation=OperationKind.DOCTOR,
            )
            return DoctorSnapshot.unavailable()

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
