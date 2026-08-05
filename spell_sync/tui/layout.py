"""Shared TUI layout primitives — one visual contract for all screens.

See docs/TUI_LAYOUT.md.
"""

from __future__ import annotations

from collections.abc import Iterable

from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Button, Static

# Expected wall times for user-facing waits (seconds). Show a hint when >= 5.
EXPECTED_DURATION_SECONDS: dict[str, int] = {
    "pull": 20,
    "push": 45,
    "recover": 25,
    "cleanup": 15,
    "discard": 10,
    "setup": 8,
    "targets": 6,
    "doctor": 10,
    "status": 6,
    "pull_preview": 12,
    "push_preview": 20,
    "recovery_preview": 10,
    "support_export": 15,
    "history_load": 5,
    "dashboard": 3,
    "targets_refresh": 8,
}

_HINT_THRESHOLD_SECONDS = 5


def expected_duration_hint(operation_key: str) -> str | None:
    """Human hint when an operation usually takes 5+ seconds; else None."""
    seconds = EXPECTED_DURATION_SECONDS.get(operation_key)
    if seconds is None or seconds < _HINT_THRESHOLD_SECONDS:
        return None
    if seconds < 60:
        return f"Usually takes about {seconds} seconds."
    minutes = max(1, round(seconds / 60))
    unit = "minute" if minutes == 1 else "minutes"
    return f"Usually takes about {minutes} {unit}."


def loading_message(label: str, operation_key: str) -> str:
    """Loading line with optional duration hint."""
    hint = expected_duration_hint(operation_key)
    if hint is None:
        return label
    return f"{label}\n{hint}"


def action_bar(
    *buttons: Button,
    status_id: str | None = None,
    status_text: str = "",
) -> Vertical:
    """Docked bottom action stack: optional status line, then equal-width buttons."""
    children: list[Widget] = []
    if status_id is not None:
        children.append(Static(status_text, id=status_id, classes="action-status"))
    children.extend(buttons)
    return Vertical(*children, id="screen-actions", classes="screen-actions")


def section_label(text: str) -> Static:
    return Static(text, classes="section-label")


def primary_back_actions(
    *,
    primary_label: str,
    primary_id: str,
    back: bool = True,
    extra: Iterable[Button] = (),
) -> Vertical:
    """Primary action first, then extras, then Back — shared ordering rule."""
    buttons: list[Button] = [
        Button(primary_label, id=primary_id, variant="primary"),
        *extra,
    ]
    if back:
        buttons.append(Button("Back", id="btn-back"))
    return action_bar(*buttons)
