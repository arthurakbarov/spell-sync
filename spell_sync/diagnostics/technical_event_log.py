"""Structured technical event file logging."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ..application.events import EventId, TechnicalEvent
from .safe_log import sanitize_log_message
from .technical_logging import get_spell_sync_logger

SCHEMA_VERSION = 1

_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "message",
        "payload",
        "path",
        "words",
        "raw_config",
        "environment",
        "exception_text",
        "journal_payload",
        "wordlist",
        "dictionary",
    }
)


def technical_event_to_dict(
    event: TechnicalEvent,
    *,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    when = timestamp or datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "timestamp": when.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "eventId": event.event_id.value,
        "operation": event.operation.value,
        "category": event.category.value,
        "severity": event.severity.value,
    }
    if event.phase is not None:
        payload["phase"] = event.phase.value
    if event.correlation_id is not None:
        payload["correlationId"] = event.correlation_id
    if event.target_id is not None:
        payload["targetId"] = event.target_id
    if event.reason_code is not None:
        payload["reasonCode"] = event.reason_code
    if event.outcome is not None:
        payload["outcome"] = event.outcome
    if event.completed is not None:
        payload["completed"] = event.completed
    if event.total is not None:
        payload["total"] = event.total
    for key in payload:
        if key in _FORBIDDEN_PAYLOAD_KEYS:
            raise ValueError(f"forbidden technical event field: {key}")
    return payload


def serialize_technical_event(event: TechnicalEvent) -> str:
    ordered = technical_event_to_dict(event)
    return json.dumps(ordered, sort_keys=True, separators=(",", ":"))


def write_technical_event(event: TechnicalEvent) -> None:
    line = serialize_technical_event(event)
    logger = get_spell_sync_logger()
    logger.info(line, extra={"structured_event": True})


def parse_technical_log_line(line: str) -> dict[str, Any] | None:
    stripped = line.strip()
    if not stripped.startswith("{"):
        return None
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("schemaVersion") != SCHEMA_VERSION:
        return None
    event_id = data.get("eventId")
    if not isinstance(event_id, str) or event_id not in {item.value for item in EventId}:
        return None
    return data


def format_log_line_for_display(line: str) -> str:
    parsed = parse_technical_log_line(line)
    if parsed is None:
        return sanitize_log_message(line)
    event_id = parsed.get("eventId", "unknown")
    severity = parsed.get("severity", "info")
    target = parsed.get("targetId")
    suffix = f" target={target}" if target else ""
    return sanitize_log_message(f"{severity} {event_id}{suffix}")
