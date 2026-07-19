"""In-memory guided review session state (not persisted)."""

from __future__ import annotations

from dataclasses import dataclass

from .reports import OperationOutcome, OperationReport, PullPreview, PushPreview


@dataclass
class ReviewSession:
    """Controller-owned review workflow state. Not a transaction or history record."""

    pull_preview: PullPreview | None = None
    pull_report: OperationReport | None = None
    push_preview: PushPreview | None = None
    push_report: OperationReport | None = None
    pull_skipped: bool = False
    push_skipped: bool = False
    push_preview_plan_before_pull: str | None = None


@dataclass(frozen=True)
class ReviewSessionReport:
    pull_status: str
    push_status: str
    recovery_note: str
    summary_lines: tuple[str, ...]


def build_review_session_report(
    session: ReviewSession,
    *,
    pending_recovery: bool = False,
) -> ReviewSessionReport:
    pull_status = _pull_status(session)
    push_status = _push_status(session)
    if pending_recovery or _session_requires_recovery(session):
        recovery_note = "Recovery is required before another write operation."
    else:
        recovery_note = "No recovery is required."
    lines = (
        "Review complete",
        "",
        f"Pull: {pull_status}",
        f"Push: {push_status}",
        "",
        recovery_note,
    )
    return ReviewSessionReport(
        pull_status=pull_status,
        push_status=push_status,
        recovery_note=recovery_note,
        summary_lines=lines,
    )


def _pull_status(session: ReviewSession) -> str:
    if session.pull_skipped:
        return "Skipped"
    report = session.pull_report
    if report is None:
        return "Not started"
    if report.outcome is OperationOutcome.COMPLETED:
        return "Completed"
    if report.outcome is OperationOutcome.COMPLETED_WITH_WARNINGS:
        return "Completed with warnings"
    if report.outcome is OperationOutcome.STOPPED_SAFELY:
        return "Stopped safely"
    if report.outcome is OperationOutcome.RECOVERY_REQUIRED:
        return "Recovery required"
    return "Failed"


def _push_status(session: ReviewSession) -> str:
    if session.push_skipped:
        return "Skipped"
    report = session.push_report
    if report is None:
        preview = session.push_preview
        if preview is not None and preview.is_executable and preview.targets_to_update == 0:
            if preview.additions == 0 and preview.removals == 0:
                return "No changes"
        return "Not started"
    if report.outcome is OperationOutcome.COMPLETED:
        if report.target_updates and all(
            row.additions == 0 and row.removals == 0 for row in report.target_updates
        ):
            return "No changes"
        return "Completed"
    if report.outcome is OperationOutcome.COMPLETED_WITH_WARNINGS:
        return "Completed with warnings"
    if report.outcome is OperationOutcome.STOPPED_SAFELY:
        return "Stopped safely"
    if report.outcome is OperationOutcome.RECOVERY_REQUIRED:
        return "Recovery required"
    return "Failed"


def _session_requires_recovery(session: ReviewSession) -> bool:
    for report in (session.pull_report, session.push_report):
        if report is not None and (
            report.recovery_required or report.outcome is OperationOutcome.RECOVERY_REQUIRED
        ):
            return True
    return False
