"""Application layer shared by CLI and TUI."""

from .events import EventLevel, EventSink, OperationEvent, OperationKind
from .reports import (
    DashboardIssue,
    DashboardSeverity,
    DashboardState,
    DoctorCheckView,
    DoctorSnapshot,
    PushExecution,
    PushPreview,
    StatusDetailSnapshot,
    StatusSnapshot,
    TargetPreview,
    TargetStatusRow,
)
from .service import SpellSyncService

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
    "PushExecution",
    "PushPreview",
    "SpellSyncService",
    "StatusDetailSnapshot",
    "StatusSnapshot",
    "TargetPreview",
    "TargetStatusRow",
]
