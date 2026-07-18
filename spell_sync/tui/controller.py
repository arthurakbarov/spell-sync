"""TUI controller over the application service."""

from __future__ import annotations

from typing import Protocol

from ..application.reports import DashboardState, PushPreviewSnapshot, StatusSnapshot
from ..cli_options import CliOptions


class TuiService(Protocol):
    def load_dashboard(self, opts: CliOptions) -> DashboardState: ...

    def load_status(self, opts: CliOptions) -> StatusSnapshot: ...

    def load_push_preview(self, opts: CliOptions) -> PushPreviewSnapshot: ...


class TuiController:
    def __init__(self, service: TuiService, opts: CliOptions) -> None:
        self._service = service
        self.opts = opts

    def dashboard(self) -> DashboardState:
        return self._service.load_dashboard(self.opts)

    def status(self) -> StatusSnapshot:
        return self._service.load_status(self.opts)

    def preview(self) -> PushPreviewSnapshot:
        return self._service.load_push_preview(self.opts)
