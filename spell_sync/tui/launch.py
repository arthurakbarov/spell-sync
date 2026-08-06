"""Launch the Textual UI."""

from __future__ import annotations

from ..application import SpellSyncService
from ..application.requests import ProjectRef
from ..diagnostics.debug_mode import emit_debug_traceback
from ..log import log
from .app import run_app
from .controller import TuiController

# Expected launch-time failures (missing display, import/runtime config, I/O).
_EXPECTED_LAUNCH_ERRORS = (
    OSError,
    RuntimeError,
    ImportError,
    ValueError,
)


def run_ui(project: ProjectRef) -> int:
    try:
        controller = TuiController(SpellSyncService(), project)
        return run_app(controller)
    except _EXPECTED_LAUNCH_ERRORS:
        log.error("TUI failed to start.")
        return 1
    except Exception as exc:
        # Unexpected: keep the same privacy-safe user message; optional stderr traceback.
        emit_debug_traceback(exc)
        log.error("TUI failed to start.")
        return 1
