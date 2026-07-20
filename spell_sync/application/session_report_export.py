"""Safe export for guided review session reports."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..diagnostics.paths import resolve_app_state_paths
from ..runtime import installed_package_version
from .reports import OperationOutcome
from .review_session import ReviewSession, build_review_session_report


@dataclass(frozen=True)
class SessionReportExport:
    schema_version: int
    generated_at: str
    spell_sync_version: str
    pull_status: str
    push_status: str
    recovery_note: str
    pull_planned_additions: int | None
    pull_actual_additions: int | None
    pull_skipped_sources: int | None
    push_planned_updates: int | None
    push_actual_updates: int | None
    push_skipped_targets: int | None
    recovery_required: bool


def build_session_report_export(
    session: ReviewSession,
    *,
    pending_recovery: bool = False,
) -> SessionReportExport:
    summary = build_review_session_report(session, pending_recovery=pending_recovery)
    pull_report = session.pull_report
    push_report = session.push_report
    push_preview = session.push_preview
    pull_preview = session.pull_preview
    pull_planned = pull_preview.additions if pull_preview is not None else None
    pull_skipped = len(pull_preview.sources_skipped) if pull_preview is not None else None
    pull_actual = None
    if pull_report is not None and pull_report.outcome in {
        OperationOutcome.COMPLETED,
        OperationOutcome.COMPLETED_WITH_WARNINGS,
    }:
        pull_actual = pull_planned
    push_planned = push_preview.targets_to_update if push_preview is not None else None
    push_actual = None
    push_skipped = None
    if push_report is not None and push_report.target_updates:
        push_actual = sum(1 for row in push_report.target_updates if row.status == "Updated")
        push_skipped = sum(
            1 for row in push_report.target_updates if row.status.startswith("Skipped")
        )
    return SessionReportExport(
        schema_version=1,
        generated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        spell_sync_version=installed_package_version(),
        pull_status=summary.pull_status,
        push_status=summary.push_status,
        recovery_note=summary.recovery_note,
        pull_planned_additions=pull_planned if not session.pull_skipped else None,
        pull_actual_additions=pull_actual if not session.pull_skipped else None,
        pull_skipped_sources=pull_skipped if not session.pull_skipped else None,
        push_planned_updates=push_planned if not session.push_skipped else None,
        push_actual_updates=push_actual if not session.push_skipped else None,
        push_skipped_targets=push_skipped if not session.push_skipped else None,
        recovery_required=pending_recovery or _recovery_required(session),
    )


def _recovery_required(session: ReviewSession) -> bool:
    for report in (session.pull_report, session.push_report):
        if report is not None and report.outcome is OperationOutcome.RECOVERY_REQUIRED:
            return True
    return False


def default_session_report_path(state_root: Path | None = None, *, fmt: str = "json") -> Path:
    root = resolve_app_state_paths(state_root=state_root).state_directory / "session-reports"
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    extension = "json" if fmt == "json" else "txt"
    candidate = root / f"review-report-{stamp}.{extension}"
    counter = 1
    while candidate.exists():
        candidate = root / f"review-report-{stamp}-{counter}.{extension}"
        counter += 1
    return candidate


def export_session_report(
    export: SessionReportExport,
    *,
    output_path: Path,
    fmt: str,
) -> Path:
    if output_path.exists():
        raise FileExistsError(f"Report already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        body = json.dumps(asdict(export), indent=2, sort_keys=True) + "\n"
    elif fmt == "text":
        body = (
            "Review session report\n\n"
            f"Generated: {export.generated_at}\n"
            f"Pull: {export.pull_status}\n"
            f"Push: {export.push_status}\n\n"
            f"{export.recovery_note}\n"
        )
    else:
        raise ValueError(f"Unsupported format: {fmt}")
    temp = output_path.with_suffix(output_path.suffix + ".tmp")
    temp.write_text(body, encoding="utf-8")
    temp.replace(output_path)
    return output_path
