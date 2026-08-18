"""Translate completed executions into UI-neutral :class:`OperationReport` values.

Kept separate from the preview/snapshot builders: these functions run *after* an
operation and only shape its outcome for presentation, with no filesystem or
dictionary reads of their own.
"""

from ..guest_messages import RECOVERY_CLEANUP_TITLE, RECOVERY_DISCARDED_TITLE
from ..sync_models import PushResult
from .field_blocks import format_aligned_fields
from .operation_explanations import (
    build_push_target_updates,
    format_pull_planned_actual_lines,
    format_push_planned_actual_lines,
    pull_report_metadata_lines,
    push_report_metadata_lines,
)
from .product_concepts import (
    pull_completed_summary,
    push_completed_summary,
    push_completed_with_skips_summary,
    written_includes_editors,
)
from .reports import (
    OperationOutcome,
    OperationReport,
    PullExecution,
    PushExecution,
    RecoveryExecution,
    RecoveryOutcome,
)
from .user_notices import build_notice


def _editors_updated(execution: PushExecution) -> bool:
    result = execution.result
    if isinstance(result, PushResult):
        return written_includes_editors(result.written)
    return False


def build_push_operation_report(execution: PushExecution) -> OperationReport:
    preview = execution.push_preview
    updates = execution.target_updates
    if preview is not None and isinstance(execution.result, PushResult):
        updates = build_push_target_updates(preview, execution.result)
    elif preview is not None and not updates:
        updates = build_push_target_updates(preview, None)

    planned_actual = format_push_planned_actual_lines(preview, updates)
    metadata = push_report_metadata_lines(
        preview,
        plan_verified=execution.outcome
        in {
            OperationOutcome.COMPLETED,
            OperationOutcome.COMPLETED_WITH_WARNINGS,
        },
        snapshots_cleaned=execution.outcome is OperationOutcome.COMPLETED
        and not execution.recovery_required,
    )
    detail_parts: tuple[str, ...] = (*planned_actual, *metadata)

    outcome = execution.outcome
    if outcome is OperationOutcome.RECOVERY_REQUIRED:
        notice = build_notice("rollback_incomplete")
        return OperationReport(
            operation="push",
            outcome=outcome,
            title=notice.title,
            summary=notice.explanation,
            details=(
                *detail_parts,
                notice.suggested_action or "",
                "Run Recovery before another write operation.",
            ),
            target_updates=updates,
            warnings=execution.warnings,
            recovery_required=True,
            plan_identifier=execution.plan_identifier,
        )
    if outcome is OperationOutcome.STOPPED_SAFELY:
        if execution.conflict_target:
            notice = build_notice(
                "stale_preview",
                target_id=execution.conflict_target.split(":", 1)[0]
                if ":" in execution.conflict_target
                else execution.conflict_target,
            )
            return OperationReport(
                operation="push",
                outcome=outcome,
                title=notice.title,
                summary=notice.explanation,
                details=(
                    *detail_parts,
                    notice.suggested_action or "",
                    "No conflicting file was overwritten.",
                ),
                target_updates=updates,
                conflict_target=execution.conflict_target,
                plan_identifier=execution.plan_identifier,
            )
        return OperationReport(
            operation="push",
            outcome=outcome,
            title="Update my apps stopped safely",
            summary="A write failed. Previously updated files were restored.",
            details=(*detail_parts, execution.message),
            target_updates=updates,
            warnings=execution.warnings,
            plan_identifier=execution.plan_identifier,
        )
    if outcome is OperationOutcome.COMPLETED_WITH_WARNINGS:
        result = execution.result
        skipped = len(result.skipped) if isinstance(result, PushResult) else 0
        written = len(result.written) if isinstance(result, PushResult) else 0
        notice = build_notice("application_running")
        return OperationReport(
            operation="push",
            outcome=outcome,
            title="Update my apps completed with warnings",
            summary=push_completed_with_skips_summary(
                written=written,
                skipped=skipped,
                editors_updated=_editors_updated(execution),
            ),
            details=(*detail_parts, notice.explanation),
            target_updates=updates,
            warnings=execution.warnings,
            plan_identifier=execution.plan_identifier,
        )
    if outcome is OperationOutcome.COMPLETED:
        result = execution.result
        written = len(result.written) if isinstance(result, PushResult) else 0
        return OperationReport(
            operation="push",
            outcome=outcome,
            title="Update my apps completed",
            summary=(
                push_completed_summary(written, editors_updated=_editors_updated(execution))
                if written
                else (execution.message or "Update my apps finished successfully.")
            ),
            details=detail_parts,
            target_updates=updates,
            warnings=execution.warnings,
            plan_identifier=execution.plan_identifier,
        )
    return OperationReport(
        operation="push",
        outcome=outcome,
        title="Update my apps failed",
        summary=execution.message or "Update my apps could not complete.",
        details=detail_parts,
        target_updates=updates,
        warnings=execution.warnings,
        plan_identifier=execution.plan_identifier,
    )


def build_pull_operation_report(execution: PullExecution) -> OperationReport:
    preview = execution.preview
    planned_actual = format_pull_planned_actual_lines(preview, execution)
    metadata = pull_report_metadata_lines(preview)
    detail_parts: tuple[str, ...] = (*planned_actual, *metadata)
    if execution.outcome is OperationOutcome.COMPLETED:
        return OperationReport(
            operation="pull",
            outcome=execution.outcome,
            title="Collect my words completed",
            summary=pull_completed_summary(preview.additions),
            details=detail_parts,
            warnings=execution.warnings or preview.warnings,
            plan_identifier=preview.plan_identifier,
        )
    return OperationReport(
        operation="pull",
        outcome=execution.outcome,
        title="Collect my words failed",
        summary=execution.message or "Collect my words could not complete.",
        details=detail_parts,
        warnings=execution.warnings,
        plan_identifier=preview.plan_identifier,
    )


def build_recovery_operation_report(execution: RecoveryExecution) -> OperationReport:
    outcome = execution.outcome
    if outcome is RecoveryOutcome.RECOVERED:
        return OperationReport(
            operation="recover",
            outcome=OperationOutcome.COMPLETED,
            title="Recovery completed",
            summary=execution.message,
            details=(
                *format_aligned_fields(
                    [
                        ("Restored", len(execution.restored)),
                        ("Skipped", len(execution.skipped)),
                    ]
                ),
                "Interrupted-update records: cleaned up",
            ),
            warnings=execution.warnings,
        )
    if outcome is RecoveryOutcome.RECOVERED_WITH_WARNINGS:
        return OperationReport(
            operation="recover",
            outcome=OperationOutcome.COMPLETED_WITH_WARNINGS,
            title="Recovery completed with warnings",
            summary=execution.message,
            details=tuple(execution.warnings),
            warnings=execution.warnings,
        )
    if outcome is RecoveryOutcome.CONFLICTED:
        return OperationReport(
            operation="recover",
            outcome=OperationOutcome.STOPPED_SAFELY,
            title="Recovery stopped safely",
            summary=execution.message,
            details=(
                "Recovery records and snapshots were preserved.",
                *(f"Conflict: {name}" for name in execution.conflicts),
            ),
            warnings=execution.warnings,
            recovery_required=True,
        )
    if outcome is RecoveryOutcome.RECOVERY_INCOMPLETE:
        return OperationReport(
            operation="recover",
            outcome=OperationOutcome.RECOVERY_REQUIRED,
            title="Recovery is incomplete",
            summary=execution.message,
            details=(
                "Recovery records and snapshots were preserved.",
                "Run Recovery again after resolving the failure.",
            ),
            warnings=execution.warnings,
            recovery_required=True,
        )
    if outcome is RecoveryOutcome.CLEANUP_COMPLETED:
        return OperationReport(
            operation="recover",
            outcome=OperationOutcome.COMPLETED,
            title=RECOVERY_CLEANUP_TITLE,
            summary=execution.message,
            details=("Remaining recovery artifacts were removed.",),
            warnings=execution.warnings,
        )
    if outcome is RecoveryOutcome.DISCARDED:
        return OperationReport(
            operation="recover",
            outcome=OperationOutcome.COMPLETED,
            title=RECOVERY_DISCARDED_TITLE,
            summary=execution.message,
            details=(
                "No files were restored.",
                "The current filesystem state was kept.",
            ),
            warnings=execution.warnings,
        )
    return OperationReport(
        operation="recover",
        outcome=OperationOutcome.FAILED,
        title="Recovery failed",
        summary=execution.message,
        details=(),
        warnings=execution.warnings,
        recovery_required=True,
    )


def build_setup_operation_report(execution) -> OperationReport:
    from ..project_setup.execute import ProjectSetupOutcome

    prepared = execution.prepared
    if execution.outcome is ProjectSetupOutcome.COMPLETED:
        details = [
            *format_aligned_fields(
                [
                    ("Word list", prepared.wordlist_path),
                    ("Configuration", prepared.config_path),
                    ("Enabled apps", len(prepared.enabled_targets)),
                ]
            ),
        ]
        if prepared.existing_wordlist_kept:
            details.append("The existing personal word list was kept unchanged.")
        details.append("No application dictionaries were changed.")
        return OperationReport(
            operation="setup",
            outcome=OperationOutcome.COMPLETED,
            title="Project created",
            summary=execution.message,
            details=tuple(details),
            warnings=execution.warnings,
            plan_identifier=prepared.setup_id,
        )
    if execution.outcome is ProjectSetupOutcome.STOPPED_SAFELY:
        return OperationReport(
            operation="setup",
            outcome=OperationOutcome.STOPPED_SAFELY,
            title="Project creation stopped safely",
            summary=execution.message,
            details=("No existing file was overwritten.",),
            warnings=execution.warnings,
            plan_identifier=prepared.setup_id,
        )
    if execution.outcome is ProjectSetupOutcome.SETUP_INCOMPLETE:
        return OperationReport(
            operation="setup",
            outcome=OperationOutcome.FAILED,
            title="Project setup is incomplete",
            summary=execution.message,
            details=(
                "Some newly created files could not be removed after an error.",
                "Existing files were not overwritten.",
            ),
            warnings=execution.warnings,
            plan_identifier=prepared.setup_id,
        )
    return OperationReport(
        operation="setup",
        outcome=OperationOutcome.FAILED,
        title="Project setup failed",
        summary=execution.message,
        details=(),
        warnings=execution.warnings,
        plan_identifier=prepared.setup_id,
    )


def build_target_settings_operation_report(execution) -> OperationReport:
    from ..project_setup.target_settings import TargetSettingsOutcome

    prepared = execution.prepared
    if execution.outcome is TargetSettingsOutcome.COMPLETED:
        settings_rows: list[tuple[str, object]] = [
            ("Configuration", prepared.config_path),
        ]
        if prepared.enabled_target_ids:
            settings_rows.append(
                ("Enabled", ", ".join(sorted(prepared.enabled_target_ids))),
            )
        if prepared.disabled_target_ids:
            settings_rows.append(
                ("Disabled", ", ".join(sorted(prepared.disabled_target_ids))),
            )
        details = [
            *format_aligned_fields(settings_rows),
            "No application dictionaries were changed.",
        ]
        return OperationReport(
            operation="targets",
            outcome=OperationOutcome.COMPLETED,
            title="Configuration updated",
            summary=execution.message,
            details=tuple(details),
            warnings=execution.warnings,
            plan_identifier=prepared.update_id,
        )
    if execution.outcome is TargetSettingsOutcome.STOPPED_SAFELY:
        return OperationReport(
            operation="targets",
            outcome=OperationOutcome.STOPPED_SAFELY,
            title="Configuration update stopped safely",
            summary=execution.message,
            details=("No application dictionaries were changed.",),
            warnings=execution.warnings,
            plan_identifier=prepared.update_id,
        )
    return OperationReport(
        operation="targets",
        outcome=OperationOutcome.FAILED,
        title="Configuration update failed",
        summary=execution.message,
        details=(),
        warnings=execution.warnings,
        plan_identifier=prepared.update_id,
    )
