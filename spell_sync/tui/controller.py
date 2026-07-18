"""TUI controller over the application service."""

from __future__ import annotations

from typing import Protocol

from ..application.events import EventSink
from ..application.reports import (
    DashboardState,
    DoctorSnapshot,
    OperationReport,
    PullExecution,
    PullPreview,
    PushExecution,
    PushPreview,
    StatusDetailSnapshot,
    StatusSnapshot,
)
from ..cli_options import CliOptions


class TuiService(Protocol):
    def load_dashboard(self, opts: CliOptions) -> DashboardState: ...

    def load_status(self, opts: CliOptions) -> StatusSnapshot: ...

    def load_status_detail(self, opts: CliOptions) -> StatusDetailSnapshot: ...

    def load_push_preview(self, opts: CliOptions) -> PushPreview: ...

    def load_doctor(self, opts: CliOptions) -> DoctorSnapshot: ...

    def prepare_pull(self, opts: CliOptions) -> PullPreview: ...

    def execute_pull(
        self,
        opts: CliOptions,
        preview: PullPreview,
        *,
        confirmed_plan_id: str,
        event_sink: EventSink | None = None,
    ) -> PullExecution: ...

    def execute_push_preview(
        self,
        opts: CliOptions,
        preview: PushPreview,
        *,
        confirmed_plan_id: str,
        event_sink: EventSink | None = None,
    ) -> PushExecution: ...

    def build_push_report(self, execution: PushExecution) -> OperationReport: ...

    def build_pull_report(self, execution: PullExecution) -> OperationReport: ...


class TuiController:
    def __init__(self, service: TuiService, opts: CliOptions) -> None:
        self._service = service
        self.opts = opts
        self._mutation_active = False
        self._active_push_preview: PushPreview | None = None
        self._active_pull_preview: PullPreview | None = None

    @property
    def mutation_active(self) -> bool:
        return self._mutation_active

    def begin_mutation(self) -> bool:
        if self._mutation_active:
            return False
        self._mutation_active = True
        return True

    def end_mutation(self) -> None:
        self._mutation_active = False

    def dashboard(self) -> DashboardState:
        return self._service.load_dashboard(self.opts)

    def status(self) -> StatusSnapshot:
        return self._service.load_status(self.opts)

    def status_detail(self) -> StatusDetailSnapshot:
        return self._service.load_status_detail(self.opts)

    def preview(self) -> PushPreview:
        preview = self._service.load_push_preview(self.opts)
        self._active_push_preview = preview
        return preview

    def invalidate_push_preview(self) -> None:
        self._active_push_preview = None

    def active_push_preview(self) -> PushPreview | None:
        return self._active_push_preview

    def doctor(self) -> DoctorSnapshot:
        return self._service.load_doctor(self.opts)

    def prepare_pull(self) -> PullPreview:
        preview = self._service.prepare_pull(self.opts)
        self._active_pull_preview = preview
        return preview

    def invalidate_pull_preview(self) -> None:
        self._active_pull_preview = None

    def active_pull_preview(self) -> PullPreview | None:
        return self._active_pull_preview

    def execute_pull(
        self,
        preview: PullPreview,
        *,
        event_sink: EventSink | None = None,
    ) -> PullExecution:
        return self._service.execute_pull(
            self.opts,
            preview,
            confirmed_plan_id=preview.plan_identifier,
            event_sink=event_sink,
        )

    def execute_push(
        self,
        preview: PushPreview,
        *,
        event_sink: EventSink | None = None,
    ) -> PushExecution:
        # Identity: must use this preview's prepared plan, never re-prepare.
        return self._service.execute_push_preview(
            self.opts,
            preview,
            confirmed_plan_id=preview.plan_identifier,
            event_sink=event_sink,
        )

    def push_report(self, execution: PushExecution) -> OperationReport:
        return self._service.build_push_report(execution)

    def pull_report(self, execution: PullExecution) -> OperationReport:
        return self._service.build_pull_report(execution)

    def writes_blocked(self, state: DashboardState | None = None) -> bool:
        current = state or self.dashboard()
        return current.pending_recovery or current.overall_severity.value == "blocked"
