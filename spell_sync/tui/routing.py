"""Interactive TUI launch routing."""

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
    return command is None


def print_non_interactive_usage_error() -> None:
    log.error("spell-sync requires a command when stdin or stdout is not a TTY.")
    log.info("Try `spell-sync add WORD`, `spell-sync status`, or `spell-sync --help`.")


def print_non_interactive_ui_error() -> None:
    log.error("spell-sync ui requires an interactive terminal (stdin and stdout must be TTY).")
    log.info("Try `spell-sync add WORD`, `spell-sync status`, or another non-interactive command.")
