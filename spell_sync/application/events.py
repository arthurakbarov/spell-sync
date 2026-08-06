"""Typed technical events and presentation-neutral operation progress."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..diagnostics.event_metadata import CorrelationId, EventReason, TargetId, TerminalOutcome
from ..diagnostics.technical_event_model import (
    EventCategory,
    EventId,
    EventPhase,
    EventSeverity,
    OperationKind,
    TechnicalEvent,
    TechnicalEventSink,
)


@dataclass(frozen=True, slots=True)
class PresentedEvent:
    """Human-facing event produced only at presentation boundaries."""

    operation: OperationKind
    event_id: EventId
    message: str
    severity: EventSeverity
    phase: EventPhase | None = None
    target_id: TargetId | None = None
    completed: int | None = None
    total: int | None = None


class PresentationEventSink(Protocol):
    def __call__(self, event: PresentedEvent) -> None: ...


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
            except Exception as exc:
                # Fail-open: a broken technical sink must not abort the product
                # operation. Narrow suppression; observable under SPELL_SYNC_DEBUG.
                # Do not re-emit through the same failing sink.
                from ..diagnostics.debug_mode import emit_debug_traceback

                emit_debug_traceback(exc)
        if self.presentation_sink is not None:
            from .event_presenter import present_event

            try:
                self.presentation_sink(present_event(event))
            except Exception as exc:
                # Fail-open: presentation must not abort mutation/read paths.
                # Record a static technical event without re-entering presentation.
                from ..diagnostics.debug_mode import emit_debug_traceback
                from ..diagnostics.technical_event_log import write_technical_event

                emit_debug_traceback(exc)
                try:
                    write_technical_event(
                        TechnicalEvent(
                            event_id=EventId.DIAGNOSTICS_PRESENTATION_SINK_FAILED,
                            operation=event.operation,
                            category=EventCategory.DIAGNOSTIC,
                            severity=EventSeverity.WARNING,
                        )
                    )
                except Exception:
                    pass


def operation_emitter(presentation_sink: PresentationEventSink | None) -> EventEmitter:
    from ..diagnostics.technical_event_log import write_technical_event

    return EventEmitter(
        presentation_sink=presentation_sink,
        technical_sink=write_technical_event,
    )


__all__ = [
    "CorrelationId",
    "EventCategory",
    "EventEmitter",
    "EventId",
    "EventPhase",
    "EventReason",
    "EventSeverity",
    "EventSink",
    "OperationKind",
    "PresentedEvent",
    "PresentationEventSink",
    "TargetId",
    "TechnicalEvent",
    "TechnicalEventSink",
    "TerminalOutcome",
    "operation_emitter",
]
