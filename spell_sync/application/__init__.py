"""Application layer shared by CLI and TUI."""

from .events import EventId, EventSink, OperationKind, PresentedEvent, TechnicalEvent
from .reports import (
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
    "EventId",
    "EventSink",
    "OperationKind",
    "OperationOutcome",
    "OperationReport",
    "OperationStage",
    "PresentedEvent",
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
    "TechnicalEvent",
]


def __getattr__(name: str):
    if name == "SpellSyncService":
        from .service import SpellSyncService

        return SpellSyncService
    if name == "RuntimeResolver":
        from .runtime_resolver import RuntimeResolver

        return RuntimeResolver
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
