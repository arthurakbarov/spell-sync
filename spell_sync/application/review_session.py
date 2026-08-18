"""In-memory guided review session state (not persisted)."""

from dataclasses import dataclass

from .field_blocks import format_aligned_fields
from .product_concepts import (
    COLLECT_WORDS_LABEL,
    RECOVERY_CLEANUP_REMAINING,
    UPDATE_APPS_LABEL,
)
from .reports import OperationOutcome, OperationReport, PullPreview, PushPreview

_MATCHED_STATUSES = frozenset({"Completed", "No changes"})


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
    is_matched: bool = False


def build_review_session_report(
    session: ReviewSession,
    *,
    pending_recovery: bool = False,
    cleanup_pending: bool = False,
) -> ReviewSessionReport:
    pull_status = _pull_status(session)
    push_status = _push_status(session)
    if pending_recovery or _session_requires_recovery(session):
        recovery_note = "Recovery is required before another write operation."
    elif cleanup_pending:
        recovery_note = RECOVERY_CLEANUP_REMAINING
    else:
        recovery_note = "No recovery is required."
    status_block = format_aligned_fields(
        [
            (COLLECT_WORDS_LABEL, pull_status),
            (UPDATE_APPS_LABEL, push_status),
        ]
    )
    lines = (
        "Review complete",
        "",
        *status_block,
        "",
        recovery_note,
    )
    return ReviewSessionReport(
        pull_status=pull_status,
        push_status=push_status,
        recovery_note=recovery_note,
        summary_lines=lines,
        is_matched=_session_is_matched(
            pull_status=pull_status,
            push_status=push_status,
            recovery_required=recovery_note.startswith("Recovery is required"),
        ),
    )


def _session_is_matched(
    *,
    pull_status: str,
    push_status: str,
    recovery_required: bool,
) -> bool:
    # "Completed with warnings" / Skipped / Not started must not claim apps match.
    if recovery_required:
        return False
    return pull_status in _MATCHED_STATUSES and push_status in _MATCHED_STATUSES


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
        if (
            preview is not None
            and preview.is_executable
            and preview.targets_to_update == 0
            and preview.additions == 0
            and preview.removals == 0
        ):
            # Skipped/corrupt/blocked apps mean dictionaries are not fully matched.
            if preview.skipped or preview.corrupt or preview.blocked or preview.warnings:
                return "Completed with warnings"
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
