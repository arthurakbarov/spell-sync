"""Session bookend technical events for CLI/TUI operation traces.

Ensures every human-mode operation session writes to the rotating technical log
(for mid-flight investigation) without duplicating CLI presentation lines.
"""

from .diagnostics.event_metadata import TerminalOutcome
from .diagnostics.paths import resolve_app_state_paths
from .diagnostics.technical_event_log import write_technical_event
from .diagnostics.technical_event_model import (
    EventCategory,
    EventId,
    EventSeverity,
    EventStage,
    OperationKind,
    TechnicalEvent,
)
from .diagnostics.technical_logging import configure_file_logging

_KEY_TO_KIND: dict[str, OperationKind] = {
    "status": OperationKind.STATUS,
    "plan": OperationKind.PLAN,
    "pull": OperationKind.PULL,
    "push": OperationKind.PUSH,
    "doctor": OperationKind.DOCTOR,
    "recover": OperationKind.RECOVER,
    "cleanup": OperationKind.RECOVER,
    "discard": OperationKind.RECOVER,
    "init": OperationKind.SETUP,
    "setup": OperationKind.SETUP,
    "targets": OperationKind.TARGETS,
    "lint": OperationKind.LINT,
    "config-check": OperationKind.CONFIG_CHECK,
    "support-report": OperationKind.SUPPORT_REPORT,
}


def operation_kind_for_key(operation_key: str) -> OperationKind | None:
    return _KEY_TO_KIND.get(operation_key)


def ensure_technical_logging() -> None:
    configure_file_logging(resolve_app_state_paths())


def emit_operation_started(operation_key: str) -> None:
    kind = operation_kind_for_key(operation_key)
    if kind is None:
        return
    ensure_technical_logging()
    write_technical_event(
        TechnicalEvent(
            event_id=EventId.OPERATION_STARTED,
            operation=kind,
            category=EventCategory.LIFECYCLE,
            severity=EventSeverity.INFO,
            stage=EventStage.PREPARING,
        )
    )


def emit_operation_finished(
    operation_key: str,
    *,
    kind: str,
) -> None:
    """Emit terminal bookend. ``kind`` is presenter outcome: done|warn|error|abort."""
    op = operation_kind_for_key(operation_key)
    if op is None:
        return
    ensure_technical_logging()
    if kind in {"done", "warn"}:
        write_technical_event(
            TechnicalEvent(
                event_id=EventId.OPERATION_COMPLETED,
                operation=op,
                category=EventCategory.LIFECYCLE,
                severity=EventSeverity.WARNING if kind == "warn" else EventSeverity.SUCCESS,
                stage=EventStage.COMPLETED,
                outcome=TerminalOutcome.COMPLETED,
            )
        )
        return
    if kind == "abort":
        write_technical_event(
            TechnicalEvent(
                event_id=EventId.OPERATION_ABORTED,
                operation=op,
                category=EventCategory.LIFECYCLE,
                severity=EventSeverity.WARNING,
                stage=EventStage.COMPLETED,
                outcome=TerminalOutcome.STOPPED_SAFELY,
            )
        )
        return
    write_technical_event(
        TechnicalEvent(
            event_id=EventId.OPERATION_FAILED,
            operation=op,
            category=EventCategory.LIFECYCLE,
            severity=EventSeverity.ERROR,
            stage=EventStage.COMPLETED,
            outcome=TerminalOutcome.FAILED,
        )
    )
