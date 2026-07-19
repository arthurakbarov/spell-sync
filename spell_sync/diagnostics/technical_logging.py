"""Rotating file logging configuration."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .path_guard import validate_directory_path, validate_file_path
from .paths import AppStatePaths
from .safe_log import format_safe_log_record
from .types import LoggingSetupResult, TechnicalLogSnapshot

_CONFIGURED = False
_HANDLER: RotatingFileHandler | None = None
_CONFIGURED_LOG: Path | None = None

MAX_BYTES = 1024 * 1024
BACKUP_COUNT = 5
SPELL_SYNC_LOGGER = "spell_sync"


class _SafeFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return format_safe_log_record(record, super().format(record))


def configure_file_logging(paths: AppStatePaths) -> LoggingSetupResult:
    global _CONFIGURED, _HANDLER, _CONFIGURED_LOG
    logger = logging.getLogger(SPELL_SYNC_LOGGER)
    if _CONFIGURED and _HANDLER is not None and _CONFIGURED_LOG == paths.technical_log:
        return LoggingSetupResult(ok=True, log_path=paths.technical_log)

    if _HANDLER is not None:
        logger.removeHandler(_HANDLER)
        _HANDLER.close()
        _HANDLER = None
        _CONFIGURED = False
        _CONFIGURED_LOG = None

    dir_check = validate_directory_path(paths.technical_log.parent, root=paths.log_root)
    if not dir_check.ok:
        return LoggingSetupResult(ok=False, detail=dir_check.detail)
    file_check = validate_file_path(paths.technical_log, root=paths.log_root)
    if not file_check.ok and paths.technical_log.exists():
        return LoggingSetupResult(ok=False, detail=file_check.detail)

    try:
        paths.technical_log.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            paths.technical_log,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(_SafeFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        _HANDLER = handler
        _CONFIGURED = True
        _CONFIGURED_LOG = paths.technical_log
        return LoggingSetupResult(ok=True, log_path=paths.technical_log)
    except OSError as exc:
        return LoggingSetupResult(ok=False, detail=str(exc))


def get_spell_sync_logger() -> logging.Logger:
    return logging.getLogger(SPELL_SYNC_LOGGER)


def reset_logging_for_tests() -> None:
    global _CONFIGURED, _HANDLER, _CONFIGURED_LOG
    logger = logging.getLogger(SPELL_SYNC_LOGGER)
    if _HANDLER is not None:
        logger.removeHandler(_HANDLER)
        _HANDLER.close()
        _HANDLER = None
    _CONFIGURED = False
    _CONFIGURED_LOG = None


def read_technical_log_tail(
    paths: AppStatePaths,
    *,
    max_lines: int = 200,
    max_bytes: int = 128 * 1024,
) -> TechnicalLogSnapshot:
    log_path = paths.technical_log
    read_check = validate_file_path(log_path, root=paths.log_root)
    if not read_check.ok and log_path.exists():
        return TechnicalLogSnapshot(path=log_path, lines=(), detail=read_check.detail)
    if not log_path.is_file():
        return TechnicalLogSnapshot(path=log_path, lines=(), detail="Log file not found.")
    try:
        raw = log_path.read_bytes()
    except OSError as exc:
        return TechnicalLogSnapshot(path=log_path, lines=(), detail=str(exc))
    truncated = len(raw) > max_bytes
    if truncated:
        raw = raw[-max_bytes:]
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
        truncated = True
    return TechnicalLogSnapshot(path=log_path, lines=tuple(lines), truncated=truncated)
