"""Application-facing report DTOs.

Canonical definitions live in ``spell_sync.operation_reports`` so core diagnostics
can import them without depending on the application layer. This module re-exports
those types as the stable import surface for ``application`` and ``tui``.
"""

from ..operation_reports import (
    DashboardIssue,
    DashboardSeverity,
    DashboardState,
    DoctorCheckView,
    DoctorSnapshot,
    DoctorTargetsSnapshot,
    DoctorTargetView,
    OperationOutcome,
    OperationReport,
    OperationStage,
    PullExecution,
    PullPreview,
    PullSourcePreview,
    PushExecution,
    PushPreview,
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
    "OperationStage",
    "OperationReport",
    "PullExecution",
    "PullPreview",
    "PullSourcePreview",
    "PushExecution",
    "PushPreview",
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
