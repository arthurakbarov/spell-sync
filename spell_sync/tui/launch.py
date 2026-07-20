"""Launch the Textual UI."""

from __future__ import annotations

from ..application import SpellSyncService
from ..application.requests import ProjectRef
from ..log import log
from .app import run_app
from .controller import TuiController


def run_ui(project: ProjectRef) -> int:
    try:
        controller = TuiController(SpellSyncService(), project)
        return run_app(controller)
    except Exception:
        log.error("TUI failed to start.")
        return 1
