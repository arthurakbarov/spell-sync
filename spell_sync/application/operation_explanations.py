"""Planned vs actual operation explanations shared by CLI and TUI."""

from __future__ import annotations

from ..project_setup.discovery import dictionary_family_id, target_display_name
from ..sync_models import PushResult
from .reports import (
    OperationOutcome,
    OperationReport,
    PullExecution,
    PullPreview,
    PushPreview,
    TargetUpdateReport,
)
from .user_notices import (
    UserNotice,
    build_notice,
    format_notice_action,
    format_notice_block,
    format_notice_details,
    format_notice_summary,
    format_notice_technical,
    format_skip_status,
    skip_reason_to_notice_code,
)


def dictionary_display_name(name: str) -> str:
    family = dictionary_family_id(name)
    return target_display_name(family)


def build_push_target_updates(
    preview: PushPreview,
    result: PushResult | None,
) -> tuple[TargetUpdateReport, ...]:
    if result is None:
        return _planned_target_updates(preview)
    written = set(result.written)
    skipped = set(result.skipped)
    rows: list[TargetUpdateReport] = []
    for target in preview.targets:
        name = target.name
        if name in written:
            rows.append(
                TargetUpdateReport(
                    name=name,
                    additions=target.additions,
                    removals=target.removals,
                    status="Updated",
                )
            )
        elif name in skipped:
            reason = result.skipped_reasons.get(name, "skipped")
            rows.append(
                TargetUpdateReport(
                    name=name,
                    additions=0,
                    removals=0,
                    status=format_skip_status(reason),
                    detail=skip_reason_to_notice_code(reason),
                )
            )
        elif target.additions == 0 and target.removals == 0:
            rows.append(
                TargetUpdateReport(
                    name=name,
                    additions=0,
                    removals=0,
                    status="Unchanged",
                )
            )
        else:
            rows.append(
                TargetUpdateReport(
                    name=name,
                    additions=0,
                    removals=0,
                    status="Skipped: not written",
                )
            )
    for name in preview.skipped:
        rows.append(
            TargetUpdateReport(
                name=name,
                additions=0,
                removals=0,
                status=format_skip_status("unreadable"),
                detail="target_unreadable",
            )
        )
    for name in preview.corrupt:
        rows.append(
            TargetUpdateReport(
                name=name,
                additions=0,
                removals=0,
                status=format_skip_status("corrupt"),
                detail="target_corrupt",
            )
        )
    return tuple(rows)


def format_push_planned_actual_lines(
    preview: PushPreview | None,
    updates: tuple[TargetUpdateReport, ...],
) -> tuple[str, ...]:
    if preview is None or not preview.targets:
        return ()
    actual_by_name = {row.name: row for row in updates}
    lines = ["Planned"]
    for target in preview.targets:
        label = dictionary_display_name(target.name)
        lines.append(f"{label:8} +{target.additions:2}  -{target.removals}")
    lines.append("")
    lines.append("Actual")
    for target in preview.targets:
        actual = actual_by_name.get(target.name)
        label = dictionary_display_name(target.name)
        if actual is None:
            lines.append(f"{label:8} + 0  - 0   Skipped")
            continue
        lines.append(f"{label:8} +{actual.additions:2}  -{actual.removals:2}   {actual.status}")
    return tuple(lines)


def format_pull_planned_actual_lines(
    preview: PullPreview,
    execution: PullExecution,
) -> tuple[str, ...]:
    planned = preview.additions
    actual = 0
    if isinstance(execution.result, tuple):
        before, after = execution.result
        actual = after - before
    skipped = len(preview.sources_skipped)
    lines = [
        f"Planned additions: {planned}",
        f"Actual additions: {actual}",
        f"Skipped sources: {skipped}",
    ]
    if actual != planned and preview.sources_skipped:
        for name in preview.sources_skipped:
            notice = build_notice("target_unreadable", target_id=_target_family(name))
            lines.append(f"  {dictionary_display_name(name)}: {notice.explanation}")
    return tuple(lines)


def operation_report_notices(report: OperationReport) -> tuple[UserNotice, ...]:
    notices: list[UserNotice] = []
    if report.recovery_required:
        notices.append(build_notice("rollback_incomplete"))
    if report.conflict_target:
        notices.append(
            build_notice(
                "stale_preview",
                target_id=_target_family(report.conflict_target),
            )
        )
    for warning in report.warnings:
        if "history record could not be saved" in warning.lower():
            notices.append(build_notice("history_write_failed"))
            continue
        if ":" in warning:
            _, reason = warning.split(":", maxsplit=1)
            notices.append(build_notice(skip_reason_to_notice_code(reason.strip())))
    return tuple(notices)


def format_operation_report_summary(report: OperationReport) -> str:
    notices = operation_report_notices(report)
    if notices:
        return format_notice_summary(notices[0])
    return report.summary or report.title


def format_operation_report_text(report: OperationReport) -> str:
    lines = [report.title, "", format_operation_report_summary(report), ""]
    if report.details:
        lines.extend(report.details)
        lines.append("")
    for notice in operation_report_notices(report):
        action = format_notice_action(notice)
        lines.extend(
            [
                format_notice_details(notice),
                action,
                format_notice_technical(notice),
                "",
            ]
        )
    if report.outcome is OperationOutcome.STOPPED_SAFELY and report.conflict_target:
        notice = build_notice(
            "stale_preview",
            target_id=_target_family(report.conflict_target),
        )
        lines.append(format_notice_block(notice))
    return "\n".join(line for line in lines if line).rstrip()


def push_report_metadata_lines(
    preview: PushPreview | None,
    *,
    plan_verified: bool = False,
    snapshots_cleaned: bool = False,
) -> tuple[str, ...]:
    lines: list[str] = []
    if preview is not None and preview.created_at:
        lines.append(f"Preview created: {preview.created_at}")
    if plan_verified:
        lines.append("Plan verified")
    if snapshots_cleaned:
        lines.append("Recovery snapshots cleaned")
    return tuple(lines)


def pull_report_metadata_lines(preview: PullPreview) -> tuple[str, ...]:
    if preview.created_at:
        return (f"Preview created: {preview.created_at}",)
    return ()


def recovery_blocker_notice(*, status_value: str, detail: str | None = None) -> UserNotice:
    normalized = status_value.lower()
    if normalized == "corrupt_journal":
        return build_notice("corrupt_journal", explanation=detail)
    if normalized == "recovery_in_progress":
        return build_notice("rollback_incomplete")
    return build_notice("pending_recovery")


def target_settings_blocker_notice(load_error: str | None) -> UserNotice | None:
    if not load_error:
        return None
    if "changed after the preview" in load_error.lower():
        return build_notice("stale_preview")
    return build_notice("invalid_config", explanation=load_error)


def _planned_target_updates(preview: PushPreview) -> tuple[TargetUpdateReport, ...]:
    rows: list[TargetUpdateReport] = []
    for target in preview.targets:
        rows.append(
            TargetUpdateReport(
                name=target.name,
                additions=target.additions,
                removals=target.removals,
                status=target.status,
            )
        )
    for name in preview.skipped:
        rows.append(TargetUpdateReport(name=name, additions=0, removals=0, status="Skipped"))
    for name in preview.corrupt:
        rows.append(TargetUpdateReport(name=name, additions=0, removals=0, status="Corrupt"))
    return tuple(rows)


def _target_family(name: str) -> str:
    return dictionary_family_id(name)
