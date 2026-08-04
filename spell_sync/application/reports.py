"""Compatibility re-exports for report DTOs.

Canonical definitions live in ``spell_sync.operation_reports`` so core diagnostics
can import them without depending on the application layer.
"""

from __future__ import annotations

from ..operation_reports import (
    DashboardIssue,
    DashboardSeverity,
    DashboardState,
    DoctorCheckView,
    DoctorSnapshot,
    DoctorTargetsSnapshot,
    DoctorTargetView,
    OperationOutcome,
    OperationPhase,
    OperationReport,
    ProjectSetupExecutionView,
    PullExecution,
    PullPreview,
    PullSourcePreview,
    PushExecution,
    PushPreview,
    PushPreviewSnapshot,
    RecoveryExecution,
    RecoveryItemPreview,
    RecoveryOutcome,
    RecoveryPreview,
    RecoveryStatus,
    StatusDetailSnapshot,
    StatusSnapshot,
    TargetPreview,
    TargetStatusRow,
    TargetUpdateReport,
)

__all__ = [
    "DashboardIssue",
    "DashboardSeverity",
    "DashboardState",
    "DoctorCheckView",
    "DoctorSnapshot",
    "DoctorTargetView",
    "DoctorTargetsSnapshot",
    "OperationOutcome",
    "OperationPhase",
    "OperationReport",
    "ProjectSetupExecutionView",
    "PullExecution",
    "PullPreview",
    "PullSourcePreview",
    "PushExecution",
    "PushPreview",
    "PushPreviewSnapshot",
    "RecoveryExecution",
    "RecoveryItemPreview",
    "RecoveryOutcome",
    "RecoveryPreview",
    "RecoveryStatus",
    "StatusDetailSnapshot",
    "StatusSnapshot",
    "TargetPreview",
    "TargetStatusRow",
    "TargetUpdateReport",
]
