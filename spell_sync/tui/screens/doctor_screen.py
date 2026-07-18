"""Read-only doctor report."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static
from textual.worker import WorkerState

from ...application.reports import DoctorSnapshot
from ..controller import TuiController
from ..workers import LoadTokenMixin


class DoctorScreen(LoadTokenMixin, Screen[None]):
    BINDINGS = [
        ("escape", "back", "Back"),
        ("r", "run_doctor", "Run again"),
    ]

    def __init__(self, controller: TuiController) -> None:
        super().__init__()
        self._controller = controller
        self._active_token = 0

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="doctor-content")
        yield Button("Run again", id="btn-run-doctor", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        try:
            self._render_snapshot(self._controller.doctor())
        except Exception:
            self.query_one("#doctor-content", Static).update("× Doctor load failed.")

    def _level_label(self, level: str) -> str:
        if level == "failed":
            return "× Failed"
        if level == "warning":
            return "! Warning"
        return "✓ Passed"

    def _render_snapshot(self, snapshot: DoctorSnapshot) -> None:
        if snapshot.load_error:
            self.query_one("#doctor-content", Static).update(f"× {snapshot.load_error}")
            return
        group_order = [
            "Project",
            "Configuration",
            "Wordlist",
            "Dictionaries",
            "Transaction state",
            "Filesystem access",
        ]
        grouped: dict[str, list] = {group: [] for group in group_order}
        for check in snapshot.checks:
            grouped.setdefault(check.group, []).append(check)

        lines = ["Doctor", ""]
        for group in group_order:
            checks = grouped.get(group, [])
            if not checks:
                continue
            lines.append(group)
            for check in checks:
                lines.append(f"  {self._level_label(check.level)} {check.title}")
                lines.append(f"    {check.detail}")
                if check.suggested_action:
                    lines.append(f"    Action: {check.suggested_action}")
            lines.append("")
        if snapshot.has_errors:
            lines.append("Overall: × blocking issues found")
        else:
            lines.append("Overall: ✓ no blocking errors")
        self.query_one("#doctor-content", Static).update("\n".join(lines).rstrip())

    def run_doctor(self) -> None:
        self._active_token = self._begin_load()
        self.query_one("#btn-run-doctor", Button).disabled = True
        self.query_one("#doctor-content", Static).update("Running doctor...")
        self.load_doctor_worker()

    @work(thread=True, exclusive=True, group="doctor-load")
    def load_doctor_worker(self) -> DoctorSnapshot:
        try:
            return self._controller.doctor()
        except Exception:
            return DoctorSnapshot(
                checks=(),
                has_errors=True,
                load_error="Doctor report could not be loaded.",
            )

    def on_load_doctor_worker_state_changed(self, event) -> None:
        if event.state is WorkerState.RUNNING:
            return
        self.query_one("#btn-run-doctor", Button).disabled = False
        if event.state is WorkerState.ERROR:
            if self.is_mounted:
                self.query_one("#doctor-content", Static).update(
                    "× Doctor unavailable — try Run again."
                )
            return
        if event.state is not WorkerState.SUCCESS:
            return
        if not self._is_current_load(self._active_token):
            return
        self._render_snapshot(event.worker.result)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-run-doctor":
            self.action_run_doctor()

    def action_run_doctor(self) -> None:
        self.run_doctor()

    def action_back(self) -> None:
        self.app.pop_screen()
