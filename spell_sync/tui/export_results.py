"""Worker results for TUI report exports."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ReportExportResult:
    ok: bool
    path: str | None = None
    message: str | None = None
