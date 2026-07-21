"""Typed technical events and presentation-neutral operation progress."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class OperationKind(str, Enum):
    STATUS = "status"
    PLAN = "plan"
    PULL = "pull"
    PUSH = "push"
    DOCTOR = "doctor"
    RECOVER = "recover"
    SETUP = "setup"
    TARGETS = "targets"


class EventCategory(str, Enum):
    LIFECYCLE = "lifecycle"
    SAFETY = "safety"
    TARGET = "target"
    TRANSACTION = "transaction"
    RECOVERY = "recovery"
    DIAGNOSTIC = "diagnostic"


class EventSeverity(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class EventPhase(str, Enum):
    PREPARING = "preparing"
    EXECUTING = "executing"
    ROLLING_BACK = "rolling_back"
    FINALIZING = "finalizing"
    COMPLETED = "completed"


class EventId(str, Enum):
    PULL_VALIDATING = "pull.validating"
    PULL_BLOCKED = "pull.blocked"
    PULL_LOCK_ACQUIRED = "pull.lock_acquired"
    PULL_RUNTIME_CHANGED = "pull.runtime_changed"
    PULL_WORDLIST_MISMATCH = "pull.wordlist_mismatch"
    PULL_PLAN_VERIFIED = "pull.plan_verified"
    PULL_WRITE_STARTED = "pull.write_started"
    PULL_WORDLIST_CHANGED = "pull.wordlist_changed"
    PULL_WRITE_FAILED = "pull.write_failed"
    PULL_COMPLETED = "pull.completed"

    PUSH_VALIDATING = "push.validating"
    PUSH_BLOCKED = "push.blocked"
    PUSH_LOCK_ACQUIRED = "push.lock_acquired"
    PUSH_RUNTIME_CHANGED = "push.runtime_changed"
    PUSH_TARGET_CHANGED = "push.target_changed"
    PUSH_BUILDING_PLAN = "push.building_plan"
    PUSH_PLAN_FAILED = "push.plan_failed"
    PUSH_PLAN_VERIFIED = "push.plan_verified"
    PUSH_SNAPSHOTS_STARTED = "push.snapshots_started"
    PUSH_DRY_RUN_STARTED = "push.dry_run_started"
    PUSH_EXECUTION_STARTED = "push.execution_started"
    PUSH_WORDLIST_WRITE_STARTED = "push.wordlist_write_started"
    PUSH_TARGET_STARTED = "push.target_started"
    PUSH_ROLLBACK_STARTED = "push.rollback_started"
    PUSH_FINALIZING = "push.finalizing"
    PUSH_FAILED = "push.failed"
    PUSH_STOPPED_SAFELY = "push.stopped_safely"
    PUSH_RECOVERY_REQUIRED = "push.recovery_required"
    PUSH_COMPLETED = "push.completed"

    RECOVERY_VALIDATING = "recovery.validating"
    RECOVERY_BLOCKED = "recovery.blocked"
    RECOVERY_LOCK_ACQUIRED = "recovery.lock_acquired"
    RECOVERY_SNAPSHOTS_VALIDATED = "recovery.snapshots_validated"
    RECOVERY_CONFLICTS_CHECKED = "recovery.conflicts_checked"
    RECOVERY_WORDLIST_RESTORE_STARTED = "recovery.wordlist_restore_started"
    RECOVERY_TARGET_RESTORE_STARTED = "recovery.target_restore_started"
    RECOVERY_TARGET_REMOVE_STARTED = "recovery.target_remove_started"
    RECOVERY_FAILED = "recovery.failed"
    RECOVERY_CLEANUP_STARTED = "recovery.cleanup_started"
    RECOVERY_CLEANUP_COMPLETED = "recovery.cleanup_completed"
    RECOVERY_COMPLETED = "recovery.completed"

    SETUP_VALIDATING = "setup.validating"
    SETUP_LOCK_ACQUIRED = "setup.lock_acquired"
    SETUP_CONFLICTS_CHECKED = "setup.conflicts_checked"
    SETUP_DIRECTORY_CREATED = "setup.directory_created"
    SETUP_CONFIG_CREATED = "setup.config_created"
    SETUP_WHITELIST_CREATED = "setup.whitelist_created"
    SETUP_WORDLIST_CREATED = "setup.wordlist_created"
    SETUP_VERIFYING = "setup.verifying"
    SETUP_COMPLETED = "setup.completed"

    TARGETS_LOCK_ACQUIRED = "targets.lock_acquired"
    TARGETS_CONFLICTS_CHECKED = "targets.conflicts_checked"
    TARGETS_WRITE_STARTED = "targets.write_started"
    TARGETS_VERIFYING = "targets.verifying"
    TARGETS_COMPLETED = "targets.completed"

    DIAGNOSTICS_HISTORY_WRITE_FAILED = "diagnostics.history_write_failed"
    DIAGNOSTICS_LOGGING_SETUP_FAILED = "diagnostics.logging_setup_failed"


# Backward-compatible alias used by presentation consumers.
EventLevel = EventSeverity


@dataclass(frozen=True, slots=True)
class TechnicalEvent:
    event_id: EventId
    operation: OperationKind
    category: EventCategory
    severity: EventSeverity
    phase: EventPhase | None = None
    correlation_id: str | None = None
    target_id: str | None = None
    reason_code: str | None = None
    outcome: str | None = None
    completed: int | None = None
    total: int | None = None


@dataclass(frozen=True, slots=True)
class PresentedEvent:
    """Human-facing event produced only at presentation boundaries."""

    operation: OperationKind
    event_id: EventId
    message: str
    severity: EventSeverity
    phase: EventPhase | None = None
    target_id: str | None = None
    completed: int | None = None
    total: int | None = None


class PresentationEventSink(Protocol):
    def __call__(self, event: PresentedEvent) -> None: ...


class TechnicalEventSink(Protocol):
    def __call__(self, event: TechnicalEvent) -> None: ...


# Public alias: CLI/TUI pass a presentation sink.
EventSink = PresentationEventSink


@dataclass(frozen=True, slots=True)
class EventEmitter:
    presentation_sink: PresentationEventSink | None
    technical_sink: TechnicalEventSink | None

    def emit(self, event: TechnicalEvent) -> None:
        if self.technical_sink is not None:
            try:
                self.technical_sink(event)
            except Exception:
                pass
        if self.presentation_sink is not None:
            from .event_presenter import present_event

            try:
                self.presentation_sink(present_event(event))
            except Exception:
                pass


def operation_emitter(presentation_sink: PresentationEventSink | None) -> EventEmitter:
    from ..diagnostics.technical_event_log import write_technical_event

    return EventEmitter(
        presentation_sink=presentation_sink,
        technical_sink=write_technical_event,
    )
