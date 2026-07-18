"""Shared async test helpers."""

from __future__ import annotations

from textual.css.query import NoMatches


async def wait_for_text(pilot, selector: str, expected: str, *, max_pauses: int = 30):
    widget = None
    for _ in range(max_pauses):
        await pilot.pause()
        try:
            widget = pilot.app.screen.query_one(selector)
        except NoMatches:
            continue
        rendered = str(widget.render())
        if expected in rendered and "Loading" not in rendered and "Running" not in rendered:
            return widget
    if widget is None:
        widget = pilot.app.screen.query_one(selector)
    return widget
