"""UI command entry."""

from .cli_options import CliOptions
from .cli_request_adapter import project_ref


def cmd_ui(opts: CliOptions) -> int:
    from .tui.launch import run_ui

    return run_ui(project_ref(opts))
