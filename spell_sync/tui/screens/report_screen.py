"""Shared operation report screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from ...application.reports import OperationOutcome, OperationReport
from ..controller import TuiController


class ReportScreen(Screen[None]):
    BINDINGS = [("escape", "back_dashboard", "Back")]

    def __init__(self, controller: TuiController, report: OperationReport) -> None:
        super().__init__()
        self._controller = controller
        self._report = report
        self._showing_details = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="report-content")
        yield Button("Back to dashboard", id="btn-dashboard", variant="primary")
        yield Button("Open details", id="btn-details")
        yield Button("Quit", id="btn-quit", variant="error")
        if self._report.outcome is OperationOutcome.STOPPED_SAFELY and self._report.conflict_target:
            yield Button("Rebuild preview", id="btn-rebuild")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#report-content", Static).update(self._summary_text())

    def _summary_text(self) -> str:
        report = self._report
        lines = [report.title, "", report.summary, ""]
        if report.details:
            lines.extend(report.details)
            lines.append("")
        if report.target_updates:
            lines.append("Targets")
            for row in report.target_updates:
                lines.append(f"  {row.name:12} +{row.additions}  -{row.removals}  {row.status}")
            lines.append("")
        if report.warnings:
            lines.append("Warnings")
            lines.extend(f"  ! {warning}" for warning in report.warnings)
            lines.append("")
        if report.recovery_required:
            lines.append("× Recovery is required before another write operation.")
        if report.plan_identifier:
            lines.append(f"Plan id: {report.plan_identifier}")
        return "\n".join(lines).rstrip()

    def _details_text(self) -> str:
        report = self._report
        lines = [report.title, report.summary, *report.details]
        if report.conflict_target:
            lines.append(f"Conflict: {report.conflict_target}")
        lines.extend(report.warnings)
        if report.recovery_required:
            lines.append("recovery_required=true")
        return "\n".join(lines)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-dashboard":
            self.action_back_dashboard()
        elif event.button.id == "btn-details":
            self._showing_details = not self._showing_details
            text = self._details_text() if self._showing_details else self._summary_text()
            self.query_one("#report-content", Static).update(text)
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

    def action_back_dashboard(self) -> None:
        from .dashboard import DashboardScreen

        completed = self._report.outcome is OperationOutcome.COMPLETED
        if self._report.operation in {"setup", "targets"} and completed:
            while len(self.app.screen_stack) > 1:
                self.app.pop_screen()
            self.app.push_screen(DashboardScreen(self._controller))
            screen = self.app.screen
            if isinstance(screen, DashboardScreen):
                screen.action_refresh_dashboard()
            return

        while not isinstance(self.app.screen, DashboardScreen):
            if len(self.app.screen_stack) <= 1:
                break
            self.app.pop_screen()
        screen = self.app.screen
        if isinstance(screen, DashboardScreen):
            screen.action_refresh_dashboard()
