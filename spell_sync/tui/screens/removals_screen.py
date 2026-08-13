"""Scrollable word list (removals or additions)."""

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from ...application.push_preview_copy import (
    format_additions_detail_body,
    format_additions_detail_summary,
    format_removals_detail_body,
    format_removals_detail_summary,
    unique_removal_words,
    unique_reviewable_addition_words,
)
from ...application.reports import PushPreview
from ..layout import action_bar


class RemovalsScreen(Screen[None]):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(
        self,
        target_name: str,
        removal_words: frozenset[str],
        *,
        title: str | None = None,
        summary: str | None = None,
        body: str | None = None,
    ) -> None:
        super().__init__()
        self._target_name = target_name
        self._removal_words = removal_words
        self._title = title or f"Removals for {target_name}"
        self._summary = summary
        self._body = body

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="screen-body", classes="screen-body"):
            yield Static(id="removals-summary")
            yield Static(id="removals-content")
            yield action_bar(Button("Back", id="btn-back"))
        yield Footer()

    def on_mount(self) -> None:
        count = len(self._removal_words)
        summary = self._summary or f"{self._title}: {count} word(s)"
        self.query_one("#removals-summary", Static).update(summary)
        if self._body is not None:
            body = self._body
        elif count:
            body = "\n".join(sorted(self._removal_words))
        else:
            body = "No words planned for removal."
        self.query_one("#removals-content", Static).update(body)

    def action_back(self) -> None:
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_back()


def removals_screen_for_push_preview(preview: PushPreview) -> RemovalsScreen:
    """Show all planned removal words across targets.

    Preview tables often leave the cursor on the first row (frequently Unchanged
    with zero removals). Aggregate every target with removals — do not open only
    the cursor-selected row. Summary counts unique words across apps.
    """
    words = unique_removal_words(preview)
    names = [target.name for target in preview.targets if target.removal_words]
    label = ", ".join(names) if names else "all targets"
    return RemovalsScreen(
        label,
        words,
        title=f"Removals across {label}",
        summary=format_removals_detail_summary(target_label=label, preview=preview),
        body=format_removals_detail_body(preview),
    )


def additions_screen_for_push_preview(preview: PushPreview) -> RemovalsScreen:
    """Show unique small-delta addition words across targets.

    Full-sync dumps (per-app additions above ``PUSH_SMALL_DELTA_REVIEW_MAX``) are
    omitted so first-time app fills do not drown the interesting deltas.
    """
    words = unique_reviewable_addition_words(preview)
    return RemovalsScreen(
        "additions",
        words,
        title="Small-delta additions",
        summary=format_additions_detail_summary(preview),
        body=format_additions_detail_body(preview),
    )
