"""UI command entry."""

from __future__ import annotations

from .cli_options import CliOptions
from .cli_request_adapter import project_ref
from .tui.launch import run_ui


def cmd_ui(opts: CliOptions) -> int:
    return run_ui(project_ref(opts))
