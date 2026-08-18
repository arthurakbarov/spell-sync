"""Shared operation report screen."""

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from ...application.operation_explanations import (
    format_operation_report_summary,
    format_operation_report_text,
)
from ...application.product_concepts import CONTINUE_TO_UPDATE_APPS_LABEL
from ...application.reports import OperationOutcome, OperationReport
from ..context_next import continue_to_update_apps, wordlist_ready_for_update
from ..controller import TuiController
from ..layout import action_bar

_SUCCESSFUL_OUTCOMES = frozenset(
    {
        OperationOutcome.COMPLETED,
        OperationOutcome.COMPLETED_WITH_WARNINGS,
    }
)


class ReportScreen(Screen[None]):
    BINDINGS = [("escape", "back_dashboard", "Back")]

    def __init__(self, controller: TuiController, report: OperationReport) -> None:
        super().__init__()
        self._controller = controller
        self._report = report
        self._showing_details = False
        self._offer_update = self._successful_collect() and wordlist_ready_for_update(controller)

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="screen-body", classes="screen-body"):
            yield Static(id="report-content")
            buttons = []
            if self._offer_update:
                buttons.append(
                    Button(
                        CONTINUE_TO_UPDATE_APPS_LABEL,
                        id="btn-continue-update",
                        variant="primary",
                    )
                )
            buttons.extend(
                [
                    Button(
                        "Back to dashboard",
                        id="btn-dashboard",
                        variant="default" if self._offer_update else "primary",
                    ),
                    Button("Open details", id="btn-details"),
                ]
            )
            if (
                self._report.outcome is OperationOutcome.STOPPED_SAFELY
                and self._report.conflict_target
            ):
                buttons.append(Button("Rebuild preview", id="btn-rebuild"))
            buttons.append(Button("Quit", id="btn-quit", variant="error"))
            yield action_bar(*buttons)
        yield Footer()

    def _successful_collect(self) -> bool:
        return self._report.operation == "pull" and self._report.outcome in _SUCCESSFUL_OUTCOMES

    def on_mount(self) -> None:
        # Default: short outcome. Open details expands notices / technical lines.
        self.query_one("#report-content", Static).update(self._summary_text())

    def _summary_text(self) -> str:
        lines = [self._report.title, "", format_operation_report_summary(self._report)]
        if self._report.summary:
            lines.extend(["", self._report.summary])
        return "\n".join(lines).rstrip()

    def _details_text(self) -> str:
        return format_operation_report_text(self._report)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-continue-update":
            continue_to_update_apps(self.app, self._controller)
        elif event.button.id == "btn-dashboard":
            self.action_back_dashboard()
        elif event.button.id == "btn-details":
            self._showing_details = not self._showing_details
            text = self._details_text() if self._showing_details else self._summary_text()
            self.query_one("#report-content", Static).update(text)
            event.button.label = "Hide details" if self._showing_details else "Open details"
        elif event.button.id == "btn-rebuild":
            self._rebuild_preview()
        elif event.button.id == "btn-quit":
            self.app.exit(0)

    def _rebuild_preview(self) -> None:
        from .dashboard import DashboardScreen
        from .preview_screen import PreviewScreen

        while not isinstance(self.app.screen, DashboardScreen):
            if len(self.app.screen_stack) <= 1:
                break
            self.app.pop_screen()
        self.app.push_screen(PreviewScreen(self._controller, refresh_on_mount=True))

    def _refresh_dashboard(self, screen) -> None:
        """Refresh only after the screen has widgets (post-push mount)."""
        if screen.is_mounted:
            screen.action_refresh_dashboard()
        else:
            screen.call_later(screen.action_refresh_dashboard)

    def action_back_dashboard(self) -> None:
        from .dashboard import DashboardScreen

        successful = self._report.outcome in _SUCCESSFUL_OUTCOMES
        if self._report.operation in {"setup", "targets"} and successful:
            while len(self.app.screen_stack) > 1:
                self.app.pop_screen()
            screen = self.app.screen
            if not isinstance(screen, DashboardScreen):
                self.app.push_screen(DashboardScreen(self._controller))
                screen = self.app.screen
            if isinstance(screen, DashboardScreen):
                self._refresh_dashboard(screen)
            if self._report.operation == "setup":
                from .first_win_screen import FirstWinScreen

                self.app.push_screen(FirstWinScreen(self._controller))
            return

        while not isinstance(self.app.screen, DashboardScreen):
            if len(self.app.screen_stack) <= 1:
                break
            self.app.pop_screen()
        screen = self.app.screen
        if isinstance(screen, DashboardScreen):
            self._refresh_dashboard(screen)
            return
        # Setup-only stacks can leave no dashboard underneath.
        self.app.push_screen(DashboardScreen(self._controller))
        screen = self.app.screen
        if isinstance(screen, DashboardScreen):
            self._refresh_dashboard(screen)
