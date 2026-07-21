"""Helpers for constructing validated technical events."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .event_metadata import CorrelationId, EventReason, TargetId, TerminalOutcome
from .technical_event_model import (
    EventCategory,
    EventId,
    EventPhase,
    EventSeverity,
    OperationKind,
    TechnicalEvent,
)

if TYPE_CHECKING:
    from ..application.reports import OperationOutcome, RecoveryOutcome
    from ..project_setup.execute import ProjectSetupOutcome
    from ..project_setup.target_settings import TargetSettingsOutcome


def parse_correlation(value: str | None) -> CorrelationId | None:
    if value is None:
        return None
    return CorrelationId.parse(value)


def parse_target(value: str | None) -> TargetId | None:
    if value is None:
        return None
    return TargetId.parse(value)


def operation_outcome_to_terminal(outcome: OperationOutcome) -> TerminalOutcome:
    from ..application.reports import OperationOutcome as Outcome

    mapping = {
        Outcome.COMPLETED: TerminalOutcome.COMPLETED,
        Outcome.COMPLETED_WITH_WARNINGS: TerminalOutcome.COMPLETED,
        Outcome.STOPPED_SAFELY: TerminalOutcome.STOPPED_SAFELY,
        Outcome.RECOVERY_REQUIRED: TerminalOutcome.RECOVERY_REQUIRED,
        Outcome.FAILED: TerminalOutcome.FAILED,
    }
    return mapping[outcome]


def recovery_outcome_to_terminal(outcome: RecoveryOutcome) -> TerminalOutcome:
    from ..application.reports import RecoveryOutcome as Outcome

    mapping = {
        Outcome.RECOVERED: TerminalOutcome.RECOVERED,
        Outcome.RECOVERED_WITH_WARNINGS: TerminalOutcome.RECOVERED_WITH_WARNINGS,
        Outcome.CONFLICTED: TerminalOutcome.CONFLICTED,
        Outcome.RECOVERY_INCOMPLETE: TerminalOutcome.INCOMPLETE,
        Outcome.CLEANUP_COMPLETED: TerminalOutcome.CLEANUP_COMPLETED,
        Outcome.DISCARDED: TerminalOutcome.DISCARDED,
        Outcome.FAILED: TerminalOutcome.FAILED,
    }
    return mapping[outcome]


def setup_outcome_to_terminal(outcome: ProjectSetupOutcome) -> TerminalOutcome:
    from ..project_setup.execute import ProjectSetupOutcome as Outcome

    mapping = {
        Outcome.COMPLETED: TerminalOutcome.COMPLETED,
        Outcome.STOPPED_SAFELY: TerminalOutcome.STOPPED_SAFELY,
        Outcome.SETUP_INCOMPLETE: TerminalOutcome.INCOMPLETE,
        Outcome.FAILED: TerminalOutcome.FAILED,
    }
    return mapping[outcome]


def target_settings_outcome_to_terminal(outcome: TargetSettingsOutcome) -> TerminalOutcome:
    from ..project_setup.target_settings import TargetSettingsOutcome as Outcome

    mapping = {
        Outcome.COMPLETED: TerminalOutcome.COMPLETED,
        Outcome.STOPPED_SAFELY: TerminalOutcome.STOPPED_SAFELY,
        Outcome.FAILED: TerminalOutcome.FAILED,
    }
    return mapping[outcome]


def push_abort_reason_to_event_reason(reason: str | None) -> EventReason | None:
    if reason is None:
        return None
    mapping = {
        "rollback_incomplete": EventReason.ROLLBACK_INCOMPLETE,
        "journal_in_progress": EventReason.JOURNAL_INVALID,
        "journal_update_failed": EventReason.JOURNAL_INVALID,
    }
    return mapping.get(reason)


def runtime_changed_reason() -> EventReason:
    return EventReason.RUNTIME_CHANGED


def build_technical_event(
    *,
    event_id: EventId,
    operation: OperationKind,
    category: EventCategory,
    severity: EventSeverity,
    phase: EventPhase | None = None,
    correlation_id: str | CorrelationId | None = None,
    target_id: str | TargetId | None = None,
    reason: EventReason | None = None,
    outcome: object | None = None,
    completed: int | None = None,
    total: int | None = None,
) -> TechnicalEvent:
    parsed_correlation = (
        correlation_id
        if isinstance(correlation_id, CorrelationId) or correlation_id is None
        else parse_correlation(correlation_id)
    )
    parsed_target = (
        target_id
        if isinstance(target_id, TargetId) or target_id is None
        else parse_target(target_id)
    )
    parsed_outcome = outcome if isinstance(outcome, TerminalOutcome) or outcome is None else None
    if parsed_outcome is None and outcome is not None:
        from ..application.reports import OperationOutcome, RecoveryOutcome

        if isinstance(outcome, OperationOutcome):
            parsed_outcome = operation_outcome_to_terminal(outcome)
        elif isinstance(outcome, RecoveryOutcome):
            parsed_outcome = recovery_outcome_to_terminal(outcome)
    return TechnicalEvent(
        event_id=event_id,
        operation=operation,
        category=category,
        severity=severity,
        phase=phase,
        correlation_id=parsed_correlation,
        target_id=parsed_target,
        reason=reason,
        outcome=parsed_outcome,
        completed=completed,
        total=total,
    )
