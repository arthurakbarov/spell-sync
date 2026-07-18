"""Launch the Textual UI."""

from __future__ import annotations

from ..application import SpellSyncService
from ..cli_options import CliOptions
from ..log import log
from .app import run_app
from .controller import TuiController


def cmd_ui(opts: CliOptions) -> int:
    try:
        controller = TuiController(SpellSyncService(), opts)
        return run_app(controller)
    except Exception:
        log.error("TUI failed to start.")
        return 1
