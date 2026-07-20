"""Application layer shared by CLI and TUI."""

from .events import EventLevel, EventSink, OperationEvent, OperationKind
from .reports import (
    DashboardIssue,
    DashboardSeverity,
    DashboardState,
    DoctorCheckView,
    DoctorSnapshot,
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
    "EventLevel",
    "EventSink",
    "OperationEvent",
    "OperationKind",
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
    "RuntimeResolver",
    "SpellSyncService",
    "StatusDetailSnapshot",
    "StatusSnapshot",
    "TargetPreview",
    "TargetStatusRow",
    "TargetUpdateReport",
]


def __getattr__(name: str):
    if name == "SpellSyncService":
        from .service import SpellSyncService

        return SpellSyncService
    if name == "RuntimeResolver":
        from .runtime_resolver import RuntimeResolver

        return RuntimeResolver
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
