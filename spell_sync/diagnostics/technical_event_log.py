"""Structured technical event file logging."""

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from .event_metadata import (
    CorrelationId,
    EventReason,
    TargetId,
    TerminalOutcome,
)
from .safe_log import sanitize_log_message
from .technical_event_model import (
    EventCategory,
    EventId,
    EventSeverity,
    EventStage,
    OperationKind,
    TechnicalEvent,
)
from .technical_logging import get_spell_sync_logger

SCHEMA_VERSION = 1
_TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
)

_ALLOWED_KEYS = frozenset(
    {
        "schemaVersion",
        "timestamp",
        "eventId",
        "operation",
        "category",
        "severity",
        "stage",
        "correlationId",
        "targetId",
        "reasonCode",
        "outcome",
        "completed",
        "total",
    }
)


@dataclass(frozen=True, slots=True)
class ParsedTechnicalLogEvent:
    event_id: EventId
    operation: OperationKind
    category: EventCategory
    severity: EventSeverity
    timestamp: str
    stage: EventStage | None = None
    correlation_id: CorrelationId | None = None
    target_id: TargetId | None = None
    reason: EventReason | None = None
    outcome: TerminalOutcome | None = None
    completed: int | None = None
    total: int | None = None


def _enum_value(enum_cls: type[Enum], raw: Any, field: str) -> str:
    if not isinstance(raw, str):
        raise ValueError(f"invalid {field} type")
    valid = {item.value for item in enum_cls}
    if raw not in valid:
        raise ValueError(f"invalid {field}")
    return raw


def validate_structured_log_message(message: str) -> str:
    """Validate logger message and return exact JSON line for file output."""
    stripped = message.strip()
    if not stripped.startswith("{") or not stripped.endswith("}"):
        raise ValueError("structured log message must be a JSON object")
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError("structured log message is not valid JSON") from exc
    validated = _validate_parsed_dict(data)
    return json.dumps(validated, sort_keys=True, separators=(",", ":"))


def _validate_parsed_dict(data: dict[str, Any]) -> dict[str, Any]:
    extra = set(data) - _ALLOWED_KEYS
    if extra:
        raise ValueError(f"unexpected structured log keys: {sorted(extra)}")
    if data.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError("unsupported schemaVersion")
    timestamp = data.get("timestamp")
    if not isinstance(timestamp, str) or not _TIMESTAMP_PATTERN.fullmatch(timestamp):
        raise ValueError("invalid timestamp")
    _enum_value(EventId, data.get("eventId"), "eventId")
    _enum_value(OperationKind, data.get("operation"), "operation")
    _enum_value(EventCategory, data.get("category"), "category")
    _enum_value(EventSeverity, data.get("severity"), "severity")
    stage = data.get("stage")
    if stage is not None:
        stage = _enum_value(EventStage, stage, "stage")
    correlation_id = data.get("correlationId")
    if correlation_id is not None:
        CorrelationId.parse(correlation_id)
    target_id = data.get("targetId")
    if target_id is not None:
        TargetId.parse(target_id)
    reason_code = data.get("reasonCode")
    if reason_code is not None:
        _enum_value(EventReason, reason_code, "reasonCode")
    outcome = data.get("outcome")
    if outcome is not None:
        _enum_value(TerminalOutcome, outcome, "outcome")
    completed = data.get("completed")
    total = data.get("total")
    if completed is not None and (
        not isinstance(completed, int) or isinstance(completed, bool) or completed < 0
    ):
        raise ValueError("invalid completed")
    if total is not None and (not isinstance(total, int) or isinstance(total, bool) or total < 0):
        raise ValueError("invalid total")
    if completed is not None and total is not None and completed > total:
        raise ValueError("completed exceeds total")
    return data


def technical_event_to_dict(
    event: TechnicalEvent,
    *,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    when = timestamp or datetime.now(UTC)
    payload: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "timestamp": when.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "eventId": event.event_id.value,
        "operation": event.operation.value,
        "category": event.category.value,
        "severity": event.severity.value,
    }
    if event.stage is not None:
        payload["stage"] = event.stage.value
    if event.correlation_id is not None:
        payload["correlationId"] = event.correlation_id.value
    if event.target_id is not None:
        payload["targetId"] = event.target_id.value
    if event.reason is not None:
        payload["reasonCode"] = event.reason.value
    if event.outcome is not None:
        payload["outcome"] = event.outcome.value
    if event.completed is not None:
        payload["completed"] = event.completed
    if event.total is not None:
        payload["total"] = event.total
    return _validate_parsed_dict(payload)


def serialize_technical_event(event: TechnicalEvent) -> str:
    return json.dumps(technical_event_to_dict(event), sort_keys=True, separators=(",", ":"))


def write_technical_event(event: TechnicalEvent) -> None:
    try:
        line = serialize_technical_event(event)
    except ValueError:
        return
    logger = get_spell_sync_logger()
    logger.info(line, extra={"structured_event": True})


def parse_technical_log_line(line: str) -> ParsedTechnicalLogEvent | None:
    stripped = line.strip()
    if not stripped.startswith("{"):
        return None
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        validated = _validate_parsed_dict(data)
    except ValueError:
        return None
    return ParsedTechnicalLogEvent(
        event_id=EventId(validated["eventId"]),
        operation=OperationKind(validated["operation"]),
        category=EventCategory(validated["category"]),
        severity=EventSeverity(validated["severity"]),
        timestamp=validated["timestamp"],
        stage=EventStage(validated["stage"]) if validated.get("stage") is not None else None,
        correlation_id=(
            CorrelationId.parse(validated["correlationId"])
            if validated.get("correlationId") is not None
            else None
        ),
        target_id=(
            TargetId.parse(validated["targetId"]) if validated.get("targetId") is not None else None
        ),
        reason=(
            EventReason(validated["reasonCode"])
            if validated.get("reasonCode") is not None
            else None
        ),
        outcome=(
            TerminalOutcome(validated["outcome"]) if validated.get("outcome") is not None else None
        ),
        completed=validated.get("completed"),
        total=validated.get("total"),
    )


def format_log_line_for_display(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("{"):
        parsed = parse_technical_log_line(line)
        if parsed is None:
            return "[malformed structured log line]"
        suffix = f" target={parsed.target_id.value}" if parsed.target_id is not None else ""
        return sanitize_log_message(f"{parsed.severity.value} {parsed.event_id.value}{suffix}")
    return sanitize_log_message(line)
