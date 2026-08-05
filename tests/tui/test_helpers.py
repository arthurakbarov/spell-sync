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
        # DataTable cells are not always present in render(); fall back to row scan.
        get_row_at = getattr(widget, "get_row_at", None)
        row_count = getattr(widget, "row_count", None)
        if callable(get_row_at) and isinstance(row_count, int):
            joined = " ".join(
                " ".join(str(cell) for cell in get_row_at(i)) for i in range(row_count)
            )
            if expected in joined and "Loading" not in joined and "Running" not in joined:
                return widget
    if widget is None:
        widget = pilot.app.screen.query_one(selector)
    return widget


async def dismiss_operation_linger(pilot, *, max_pauses: int = 30) -> None:
    """Dismiss OperationScreen after completion linger before ReportScreen."""
    for _ in range(max_pauses):
        await pilot.pause()
        try:
            close_btn = pilot.app.screen.query_one("#btn-close")
        except NoMatches:
            continue
        if not close_btn.disabled:
            await pilot.click("#btn-close")
            return
    await pilot.click("#btn-close")


async def wait_for_operation_report(pilot, expected: str, *, max_pauses: int = 30):
    await dismiss_operation_linger(pilot, max_pauses=max_pauses)
    return await wait_for_text(pilot, "#report-content", expected, max_pauses=max_pauses)
