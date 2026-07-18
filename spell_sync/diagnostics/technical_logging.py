"""Rotating file logging configuration."""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler

from .paths import AppStatePaths
from .safe_log import sanitize_log_message
from .types import LoggingSetupResult, TechnicalLogSnapshot

_CONFIGURED = False
_HANDLER: RotatingFileHandler | None = None

MAX_BYTES = 1024 * 1024
BACKUP_COUNT = 5
SPELL_SYNC_LOGGER = "spell_sync"


class _SafeFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        if isinstance(record.msg, str):
            record.msg = sanitize_log_message(record.msg)
        formatted = super().format(record)
        return _sanitize_formatted_output(formatted)


def _sanitize_formatted_output(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        if re.match(r"^\s*\w+(Error|Exception):", line):
            lines.append(re.sub(r"(:\s*).+", r"\1[sanitized exception message]", line, count=1))
            continue
        lines.append(sanitize_log_message(line))
    return "\n".join(lines)


def configure_file_logging(paths: AppStatePaths) -> LoggingSetupResult:
    global _CONFIGURED, _HANDLER
    logger = logging.getLogger(SPELL_SYNC_LOGGER)
    if _CONFIGURED and _HANDLER is not None:
        return LoggingSetupResult(ok=True, log_path=paths.technical_log)

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
        return LoggingSetupResult(ok=True, log_path=paths.technical_log)
    except OSError as exc:
        return LoggingSetupResult(ok=False, detail=str(exc))


def get_spell_sync_logger() -> logging.Logger:
    return logging.getLogger(SPELL_SYNC_LOGGER)


def reset_logging_for_tests() -> None:
    global _CONFIGURED, _HANDLER
    logger = logging.getLogger(SPELL_SYNC_LOGGER)
    if _HANDLER is not None:
        logger.removeHandler(_HANDLER)
        _HANDLER.close()
        _HANDLER = None
    _CONFIGURED = False


def read_technical_log_tail(
    paths: AppStatePaths,
    *,
    max_lines: int = 200,
    max_bytes: int = 128 * 1024,
) -> TechnicalLogSnapshot:
    log_path = paths.technical_log
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
