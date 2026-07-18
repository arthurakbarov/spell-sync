"""Read-only push preview."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from ...exit_codes import ExitCode
from ...sync_models import PushResult
from ..controller import TuiController


class PreviewScreen(Screen[None]):
    BINDINGS = [
        ("escape", "back", "Back"),
        ("r", "refresh_preview", "Refresh"),
    ]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="preview-content")
        yield DataTable(id="preview-table")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_preview()

    def refresh_preview(self) -> None:
        preview = self._controller.preview()
        table = self.query_one("#preview-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Target", "Add", "Remove", "Status")

        total_add = 0
        total_remove = 0
        for diff in preview.diffs:
            total_add += diff.to_add
            total_remove += diff.to_remove
            if diff.to_add or diff.to_remove:
                status = "Review"
            else:
                status = "Unchanged"
            table.add_row(diff.name, str(diff.to_add), str(diff.to_remove), status)

        summary = self.query_one("#preview-content", Static)
        if preview.wordlist_error is not None:
            summary.update(f"× Preview unavailable (exit {int(preview.wordlist_error)})")
            return

        plan_line = ""
        plan_result = preview.plan_result
        if isinstance(plan_result, PushResult):
            plan_line = (
                f"Plan: {plan_result.word_count} words across {len(plan_result.written)} targets"
            )
        elif isinstance(plan_result, ExitCode):
            plan_line = f"Plan blocked (exit {int(plan_result)})"

        summary.update(
            "\n".join(
                [
                    "Push preview (no writes)",
                    plan_line,
                    f"Total additions: {total_add}",
                    f"Total removals: {total_remove}",
                ]
            )
        )

    def action_refresh_preview(self) -> None:
        self.refresh_preview()

    def action_back(self) -> None:
        self.app.pop_screen()
