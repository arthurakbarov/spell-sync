"""Textual user interface for spell-sync."""

from .launch import run_ui
from .routing import (
    print_non_interactive_ui_error,
    print_non_interactive_usage_error,
    should_launch_tui,
)

__all__ = [
    "run_ui",
    "print_non_interactive_ui_error",
    "print_non_interactive_usage_error",
    "should_launch_tui",
]
