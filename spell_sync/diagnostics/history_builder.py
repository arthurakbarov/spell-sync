"""Build operation history records from typed reports."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from ..application.reports import (
    OperationReport,
    PullExecution,
    RecoveryExecution,
    RecoveryOutcome,
    TargetUpdateReport,
)
from ..project_setup.execute import ProjectSetupExecution, ProjectSetupOutcome
from ..project_setup.target_settings import TargetSettingsExecution, TargetSettingsOutcome
from .history_record import HISTORY_SCHEMA_VERSION, OperationHistoryRecord


@dataclass(frozen=True)
class HistoryBuildContext:
    duration_ms: int = 0
    started_at: datetime | None = None


def _record_id(operation: str, identifier: str | None, outcome: str) -> str:
    digest = hashlib.sha256()
    digest.update(operation.encode("utf-8"))
    digest.update(b"\0")
    digest.update(str(identifier or "").encode("utf-8"))
    digest.update(b"\0")
    digest.update(outcome.encode("utf-8"))
    return digest.hexdigest()[:16]


def _target_counts(rows: tuple[TargetUpdateReport, ...]) -> tuple[int, int, int, int, int, int]:
    updated = unchanged = skipped = failed = 0
    additions = removals = 0
    for row in rows:
        status = row.status.lower()
        if status in {"updated", "written"}:
            updated += 1
        elif status in {"unchanged", "kept"}:
            unchanged += 1
        elif status in {"skipped", "corrupt", "blocked"}:
            skipped += 1
        elif status in {"failed", "conflict"}:
            failed += 1
        additions += row.additions
        removals += row.removals
    return updated, unchanged, skipped, failed, additions, removals


def build_history_record(
    report: OperationReport,
    *,
    context: HistoryBuildContext | None = None,
    source: object | None = None,
) -> OperationHistoryRecord:
    ctx = context or HistoryBuildContext()
    timestamp = ctx.started_at or datetime.now(timezone.utc)
    identifier = report.plan_identifier
    if identifier is not None:
        identifier = str(identifier)
    setup_id: str | None = None
    transaction_id: str | None = None
    if report.operation == "setup":
        setup_id = identifier
    else:
        transaction_id = identifier

    updated, unchanged, skipped, failed, additions, removals = _target_counts(report.target_updates)
    base = OperationHistoryRecord(
        schema_version=HISTORY_SCHEMA_VERSION,
        record_id=_record_id(report.operation, identifier, report.outcome.value),
        timestamp=timestamp,
        operation=report.operation,
        outcome=report.outcome.value,
        duration_ms=ctx.duration_ms,
        updated_targets=updated,
        unchanged_targets=unchanged,
        skipped_targets=skipped,
        failed_targets=failed,
        additions=additions,
        removals=removals,
        warnings=len(report.warnings),
        transaction_id=transaction_id,
        setup_id=setup_id,
    )

    if type(source) is PullExecution:
        preview = source.preview
        return replace(
            base,
            additions=preview.additions,
            added_words=preview.additions,
            sources_used=len(preview.sources_used),
            sources_skipped=len(preview.sources_skipped),
        )
    if type(source) is RecoveryExecution:
        outcome = source.outcome
        if outcome is RecoveryOutcome.CLEANUP_COMPLETED:
            return replace(base, removed_created_files=1, outcome="cleanup_completed")
        if outcome is RecoveryOutcome.DISCARDED:
            return replace(base, outcome="discarded")
        return replace(
            base,
            restored_files=len(source.restored),
            conflicts=len(source.conflicts),
        )
    if type(source) is ProjectSetupExecution:
        prepared = source.prepared
        if source.outcome is ProjectSetupOutcome.STOPPED_SAFELY:
            return replace(base, outcome="stopped_safely", setup_id=str(prepared.setup_id))
        if source.outcome is ProjectSetupOutcome.SETUP_INCOMPLETE:
            return replace(base, outcome="setup_incomplete", setup_id=str(prepared.setup_id))
        return replace(
            base,
            created_files=len(source.created_files),
            enabled_targets=len(prepared.enabled_targets),
            setup_id=str(prepared.setup_id),
        )
    if type(source) is TargetSettingsExecution:
        target_prepared = source.prepared
        if source.outcome is TargetSettingsOutcome.STOPPED_SAFELY:
            return replace(base, outcome="stopped_safely")
        return replace(
            base,
            enabled_targets=len(target_prepared.enabled_target_ids),
            unchanged_targets=len(target_prepared.disabled_target_ids),
        )
    return base
