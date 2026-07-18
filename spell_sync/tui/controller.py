"""TUI controller over the application service."""

from __future__ import annotations

from typing import Protocol

from ..application.reports import (
    DashboardState,
    DoctorSnapshot,
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


class TuiController:
    def __init__(self, service: TuiService, opts: CliOptions) -> None:
        self._service = service
        self.opts = opts

    def dashboard(self) -> DashboardState:
        return self._service.load_dashboard(self.opts)

    def status(self) -> StatusSnapshot:
        return self._service.load_status(self.opts)

    def status_detail(self) -> StatusDetailSnapshot:
        return self._service.load_status_detail(self.opts)

    def preview(self) -> PushPreview:
        return self._service.load_push_preview(self.opts)

    def doctor(self) -> DoctorSnapshot:
        return self._service.load_doctor(self.opts)
