"""Application-facing report DTOs.

Canonical definitions live in ``spell_sync.operation_reports`` so core diagnostics
can import them without depending on the application layer. This module re-exports
those types as the stable import surface for ``application`` and ``tui``.
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
    "OperationPhase",
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
