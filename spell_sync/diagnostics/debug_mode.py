"""Developer debug mode for unexpected failures (stderr only; default off)."""

import os
import sys
import traceback
from typing import TextIO

from .technical_event_model import (
    EventCategory,
    EventId,
    EventSeverity,
    OperationKind,
    TechnicalEvent,
)


def debug_diagnostics_enabled() -> bool:
    """True when the user explicitly enabled developer diagnostics.

    Set ``SPELL_SYNC_DEBUG=1`` (also ``true`` / ``yes`` / ``on``). Default off.
    Never writes to stdout — JSON CLI contracts must stay intact.
    """
    raw = os.environ.get("SPELL_SYNC_DEBUG", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def emit_debug_traceback(exc: BaseException, *, stream: TextIO | None = None) -> None:
    """Print a traceback to stderr when debug diagnostics are enabled."""
    if not debug_diagnostics_enabled():
        return
    try:
        out = sys.stderr if stream is None else stream
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=out)
    except Exception:
        # Fail-open: a broken stderr must not abort the product path.
        pass


def emit_boundary_technical_event(
    event_id: EventId,
    *,
    operation: OperationKind,
) -> None:
    """Record a low-cardinality unexpected-boundary event (no exception payload)."""
    try:
        from .technical_event_log import write_technical_event

        write_technical_event(
            TechnicalEvent(
                event_id=event_id,
                operation=operation,
                category=EventCategory.DIAGNOSTIC,
                severity=EventSeverity.ERROR,
            )
        )
    except Exception:
        # Fail-open: diagnostics must not break the product path.
        pass
