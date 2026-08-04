"""Result types for diagnostics storage and reads."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..operation_reports import OperationOutcome
from .history_record import OperationHistoryRecord
from .technical_event_model import OperationKind


@dataclass(frozen=True)
class HistoryWriteResult:
    ok: bool
    record_id: str | None = None
    duplicate: bool = False
    detail: str | None = None


@dataclass(frozen=True)
class HistoryReadResult:
    records: tuple[OperationHistoryRecord, ...]
    malformed_lines: int = 0
    detail: str | None = None


@dataclass(frozen=True)
class HistoryClearResult:
    ok: bool
    detail: str | None = None


@dataclass(frozen=True)
class OperationHistorySnapshot:
    records: tuple[OperationHistoryRecord, ...]
    malformed_lines: int = 0
    detail: str | None = None


@dataclass(frozen=True)
class TechnicalLogSnapshot:
    path: Path
    lines: tuple[str, ...]
    truncated: bool = False
    detail: str | None = None


@dataclass(frozen=True)
class LoggingSetupResult:
    ok: bool
    log_path: Path | None = None
    detail: str | None = None


HistoryOperationFilter = OperationKind | None
HistoryOutcomeFilter = OperationOutcome | None
