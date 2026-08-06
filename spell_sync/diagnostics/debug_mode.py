"""Developer debug mode for unexpected failures (stderr only; default off)."""

from __future__ import annotations

import os
import sys
import traceback
from typing import TextIO


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
    out = sys.stderr if stream is None else stream
    traceback.print_exception(type(exc), exc, exc.__traceback__, file=out)


def unexpected_error_category(exc: BaseException) -> str:
    """Privacy-safe category token for structured events (type name only)."""
    return type(exc).__name__
