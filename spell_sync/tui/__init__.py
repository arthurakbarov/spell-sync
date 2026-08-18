"""Textual user interface for spell-sync."""

from typing import Any

from .routing import (
    print_non_interactive_ui_error,
    print_non_interactive_usage_error,
    should_launch_tui,
)

__all__ = [
    "print_non_interactive_ui_error",
    "print_non_interactive_usage_error",
    "run_ui",
    "should_launch_tui",
]


def __getattr__(name: str) -> Any:
    if name == "run_ui":
        from .launch import run_ui

        return run_ui
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
