"""Diagnostics: operation history and technical logging."""

from .history_record import OperationHistoryRecord
from .history_store import OperationHistoryStore
from .paths import AppStatePaths, resolve_app_state_paths
from .technical_logging import configure_file_logging, read_technical_log_tail
from .types import (
    HistoryClearResult,
    HistoryReadResult,
    HistoryWriteResult,
    LoggingSetupResult,
    OperationHistorySnapshot,
    TechnicalLogSnapshot,
)

__all__ = [
    "AppStatePaths",
    "HistoryClearResult",
    "HistoryReadResult",
    "HistoryWriteResult",
    "LoggingSetupResult",
    "OperationHistoryRecord",
    "OperationHistorySnapshot",
    "OperationHistoryStore",
    "TechnicalLogSnapshot",
    "configure_file_logging",
    "read_technical_log_tail",
    "resolve_app_state_paths",
]
