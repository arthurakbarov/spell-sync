"""Re-export validated metadata from diagnostics."""

from ..diagnostics.event_metadata import (
    CorrelationId,
    EventReason,
    TargetId,
    TerminalOutcome,
)

__all__ = [
    "CorrelationId",
    "EventReason",
    "TargetId",
    "TerminalOutcome",
]
