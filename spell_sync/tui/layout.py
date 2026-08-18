"""Shared TUI layout primitives — one visual contract for all screens.

Duration hints and action-bar rules live with the product operation presenter.
"""

from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Button, DataTable, Static

from ..operation_timing import INITIAL_EXPECTED_SECONDS, eta_line

# Re-export for tests and call sites that mutate the registry in-process.
EXPECTED_DURATION_SECONDS = INITIAL_EXPECTED_SECONDS


def expected_duration_hint(operation_key: str) -> str | None:
    """Human hint when an operation usually takes 5+ seconds; else None."""
    return eta_line(operation_key)


def loading_message(label: str, operation_key: str) -> str:
    """Loading line with optional duration hint.

    Guest ellipsis is three ASCII periods (U+2026 is normalized away).
    """
    label = label.replace("\u2026", "...")
    hint = expected_duration_hint(operation_key)
    if hint is None:
        return label
    return f"{label}\n{hint}"


def sync_data_table_rows(table: DataTable) -> None:
    """Show a DataTable only when it has rows.

    Empty tables must not reserve ``min-height`` — that reads as a layout hole
    between a summary label and the next prose (see ``docs/internal/TUI_LAYOUT.md``).
    Populated tables take the ``-populated`` class so CSS can keep a stable height.
    """
    populated = table.row_count > 0
    table.set_class(populated, "-populated")
    table.display = populated


def set_optional_static(widget: Static, text: str) -> None:
    """Update a status/placeholder Static and hide it when blank.

    Empty widgets that keep ``display`` still contribute CSS margin and open a
    hole above the next control (Review complete / action-status regression).
    Always use this (or the same display sync) when writing optional status text.
    """
    content = text.strip()
    widget.update(content)
    widget.display = bool(content)


def action_bar(
    *buttons: Button,
    status_id: str | None = None,
    status_text: str = "",
    extra_classes: str = "",
    bar_id: str = "screen-actions",
) -> Vertical:
    """Inline equal-width action stack for the end of ``#screen-body`` scroll.

    Callers must yield this inside the body ``VerticalScroll`` (not as a docked
    sibling). Optional status line sits above the buttons.
    """
    children: list[Widget] = []
    if status_id is not None:
        status = Static(status_text, id=status_id, classes="action-status")
        # Blank status must not keep margin and push the primary button down.
        status.display = bool(status_text.strip())
        children.append(status)
    children.extend(buttons)
    classes = "screen-actions"
    if extra_classes.strip():
        classes = f"{classes} {extra_classes.strip()}"
    return Vertical(*children, id=bar_id, classes=classes)


def targets_inline_actions(
    *,
    primary_label: str,
    primary_id: str,
    status_id: str = "targets-status",
) -> Vertical:
    """Targets checklist actions — same inline stack rules as ``action_bar``."""
    return action_bar(
        Button(primary_label, id=primary_id, variant="primary"),
        Button("Select", id="btn-select-available"),
        Button("Clear", id="btn-clear"),
        Button("Back", id="btn-back"),
        status_id=status_id,
        extra_classes="targets-inline-actions",
        bar_id="targets-actions",
    )


def section_label(text: str) -> Static:
    """Bold rule-style group header (``── Usual path``) above a button cluster."""
    return Static(f"── {text}", classes="section-label")


def menu_item(
    button: Button,
    hint: str | None = None,
    *,
    hint_id: str | None = None,
    item_id: str | None = None,
    visible: bool = True,
) -> Vertical:
    """Dashboard menu unit: button with optional caption under it.

    The caption stays left-aligned with the button but may be wider so prose
    does not wrap inside the button's 36-column box. When hiding a conditional
    action, set ``display`` on this Vertical (via ``item_id``), not only the
    button — an empty ``.menu-item`` still keeps its top margin.
    """
    children: list[Widget] = [button]
    if hint is not None and hint.strip():
        children.append(Static(hint.strip(), id=hint_id, classes="menu-item-hint"))
    item = (
        Vertical(*children, id=item_id, classes="menu-item")
        if item_id is not None
        else Vertical(*children, classes="menu-item")
    )
    item.display = visible
    return item
