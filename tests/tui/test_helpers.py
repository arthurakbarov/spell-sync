"""Shared async test helpers."""

from textual.css.query import NoMatches

_TRANSIENT_HEADS = (
    "Loading",
    "Running doctor",
    "Running…",
    "Running...",
    "Refreshing",
    "Saving report",
    "Exporting",
)


def _is_transient_loading(text: str) -> bool:
    """True while a screen shows an in-progress head line (not body copy)."""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        return stripped.startswith(_TRANSIENT_HEADS)
    return False


def _widget_text(widget) -> str:
    """Collect visible text from a widget and simple children (rows/checkboxes)."""
    chunks: list[str] = [str(widget.render())]
    label = getattr(widget, "label", None)
    if label is not None:
        chunks.append(str(label))
    for child in getattr(widget, "children", ()):
        try:
            chunks.append(str(child.render()))
        except Exception:
            pass
        child_label = getattr(child, "label", None)
        if child_label is not None:
            chunks.append(str(child_label))
    return "\n".join(chunks)


async def wait_for_text(pilot, selector: str, expected: str, *, max_pauses: int = 30):
    widget = None
    rendered = ""
    joined = ""
    for _ in range(max_pauses):
        await pilot.pause()
        try:
            widget = pilot.app.screen.query_one(selector)
        except NoMatches:
            continue
        rendered = _widget_text(widget)
        if expected in rendered and not _is_transient_loading(rendered):
            return widget
        # DataTable cells are not always present in render(); fall back to row scan.
        get_row_at = getattr(widget, "get_row_at", None)
        row_count = getattr(widget, "row_count", None)
        if callable(get_row_at) and isinstance(row_count, int):
            joined = " ".join(
                " ".join(str(cell) for cell in get_row_at(i)) for i in range(row_count)
            )
            if expected in joined and not _is_transient_loading(joined):
                return widget
    if widget is None:
        raise AssertionError(f"No widget matching {selector!r} while waiting for {expected!r}")
    detail = joined or rendered
    raise AssertionError(f"Timed out waiting for {expected!r} in {selector!r}; last={detail!r}")


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
