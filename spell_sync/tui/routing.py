"""Interactive TUI launch routing."""

from __future__ import annotations

from ..log import log


def should_launch_tui(
    command: str | None,
    *,
    stdin_is_tty: bool,
    stdout_is_tty: bool,
    json_requested: bool,
) -> bool:
    """Return True when argv should open the Textual dashboard."""
    if json_requested:
        return False
    if not (stdin_is_tty and stdout_is_tty):
        return False
    if command == "ui":
        return True
    if command is not None:
        return False
    return True


def print_non_interactive_usage_error() -> None:
    log.error("spell-sync requires a command when stdin or stdout is not a TTY.")
    log.info("Run `spell-sync --help` for usage.")


def print_non_interactive_ui_error() -> None:
    log.error("spell-sync ui requires an interactive terminal (stdin and stdout must be TTY).")
    log.info("Run `spell-sync status` or another subcommand for non-interactive use.")
