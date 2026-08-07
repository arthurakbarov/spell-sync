"""Versioned operation history record schema."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

HISTORY_SCHEMA_VERSION = 1
_MAX_COUNT = 10_000_000


def _clamp_count(value: int) -> int:
    if value < 0:
        return 0
    if value > _MAX_COUNT:
        return _MAX_COUNT
    return value


def _normalize_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class OperationHistoryRecord:
    schema_version: int
    record_id: str
    timestamp: datetime
    operation: str
    outcome: str
    duration_ms: int
    updated_targets: int = 0
    unchanged_targets: int = 0
    skipped_targets: int = 0
    failed_targets: int = 0
    additions: int = 0
    removals: int = 0
    warnings: int = 0
    transaction_id: str | None = None
    setup_id: str | None = None
    restored_files: int = 0
    removed_created_files: int = 0
    conflicts: int = 0
    created_files: int = 0
    enabled_targets: int = 0
    added_words: int = 0
    sources_used: int = 0
    sources_skipped: int = 0

    def to_json_dict(self) -> dict[str, Any]:
        timestamp = _normalize_timestamp(self.timestamp)
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "record_id": self.record_id,
            "timestamp": timestamp.replace(microsecond=0).isoformat(),
            "operation": self.operation,
            "outcome": self.outcome,
            "duration_ms": self.duration_ms,
            "updated_targets": self.updated_targets,
            "unchanged_targets": self.unchanged_targets,
            "skipped_targets": self.skipped_targets,
            "failed_targets": self.failed_targets,
            "additions": self.additions,
            "removals": self.removals,
            "warnings": self.warnings,
        }
        if self.transaction_id is not None:
            payload["transaction_id"] = self.transaction_id
        if self.setup_id is not None:
            payload["setup_id"] = self.setup_id
        if self.restored_files:
            payload["restored_files"] = self.restored_files
        if self.removed_created_files:
            payload["removed_created_files"] = self.removed_created_files
        if self.conflicts:
            payload["conflicts"] = self.conflicts
        if self.created_files:
            payload["created_files"] = self.created_files
        if self.enabled_targets:
            payload["enabled_targets"] = self.enabled_targets
        if self.added_words:
            payload["added_words"] = self.added_words
        if self.sources_used:
            payload["sources_used"] = self.sources_used
        if self.sources_skipped:
            payload["sources_skipped"] = self.sources_skipped
        return payload

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> OperationHistoryRecord | None:
        try:
            schema_version = int(data["schema_version"])
            if schema_version != HISTORY_SCHEMA_VERSION:
                return None
            timestamp = _normalize_timestamp(datetime.fromisoformat(str(data["timestamp"])))
            return cls(
                schema_version=schema_version,
                record_id=str(data["record_id"]),
                timestamp=timestamp,
                operation=str(data["operation"]),
                outcome=str(data["outcome"]),
                duration_ms=max(0, int(data["duration_ms"])),
                updated_targets=_clamp_count(int(data.get("updated_targets", 0))),
                unchanged_targets=_clamp_count(int(data.get("unchanged_targets", 0))),
                skipped_targets=_clamp_count(int(data.get("skipped_targets", 0))),
                failed_targets=_clamp_count(int(data.get("failed_targets", 0))),
                additions=_clamp_count(int(data.get("additions", 0))),
                removals=_clamp_count(int(data.get("removals", 0))),
                warnings=_clamp_count(int(data.get("warnings", 0))),
                transaction_id=data.get("transaction_id"),
                setup_id=data.get("setup_id"),
                restored_files=_clamp_count(int(data.get("restored_files", 0))),
                removed_created_files=_clamp_count(int(data.get("removed_created_files", 0))),
                conflicts=_clamp_count(int(data.get("conflicts", 0))),
                created_files=_clamp_count(int(data.get("created_files", 0))),
                enabled_targets=_clamp_count(int(data.get("enabled_targets", 0))),
                added_words=_clamp_count(int(data.get("added_words", 0))),
                sources_used=_clamp_count(int(data.get("sources_used", 0))),
                sources_skipped=_clamp_count(int(data.get("sources_skipped", 0))),
            )
        except (KeyError, TypeError, ValueError):
            return None
