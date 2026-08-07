"""Launch the Textual UI."""

from __future__ import annotations

from ..application import SpellSyncService
from ..application.requests import ProjectRef
from ..diagnostics.debug_mode import emit_boundary_technical_event, emit_debug_traceback
from ..diagnostics.technical_event_model import EventId, OperationKind
from ..log import log

# Expected environment/I/O failures after TUI modules import successfully.
# Generic RuntimeError/ValueError from controller/app internals are unexpected so
# SPELL_SYNC_DEBUG can surface them on stderr.
_EXPECTED_LAUNCH_ERRORS = (OSError,)


def run_ui(project: ProjectRef) -> int:
    """Start the TUI. Import failures are caught so missing Textual stays privacy-safe."""
    try:
        return _run_ui_impl(project)
    except ImportError as exc:
        emit_debug_traceback(exc)
        emit_boundary_technical_event(
            EventId.DIAGNOSTICS_TUI_LAUNCH_UNEXPECTED_FAILURE,
            operation=OperationKind.STATUS,
        )
        log.error("TUI failed to start.")
        return 1
    except _EXPECTED_LAUNCH_ERRORS:
        log.error("TUI failed to start.")
        return 1
    except Exception as exc:
        emit_debug_traceback(exc)
        emit_boundary_technical_event(
            EventId.DIAGNOSTICS_TUI_LAUNCH_UNEXPECTED_FAILURE,
            operation=OperationKind.STATUS,
        )
        log.error("TUI failed to start.")
        return 1


def _run_ui_impl(project: ProjectRef) -> int:
    # Import inside the protected path so ImportError is handled like other launch failures.
    from .app import run_app
    from .controller import TuiController

    controller = TuiController(SpellSyncService(), project)
    return run_app(controller)
