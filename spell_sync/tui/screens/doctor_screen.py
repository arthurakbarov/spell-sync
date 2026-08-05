"""Read-only doctor report."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Static
from textual.worker import Worker, WorkerState

from ...application.reports import DoctorSnapshot
from ...support.path_redaction import redact_path
from ..controller import TuiController
from ..export_results import ReportExportResult
from ..layout import action_bar, loading_message
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
        self._export_generation = 0
        self._export_in_progress = False
        self._export_token = 0
        self._export_started_token = 0
        self._export_worker_handle: Worker | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="screen-body", classes="screen-body"):
            yield Static(id="doctor-summary", classes="screen-prose")
            yield DataTable(id="doctor-table")
        yield action_bar(
            Button("Run again", id="btn-run-doctor", variant="primary"),
            Button("Export support report", id="btn-export-support"),
            Button("Technical details (support)", id="btn-tech-log"),
            Button("Back", id="btn-back"),
            status_id="doctor-export-status",
        )
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#doctor-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Group", "Result", "Check", "Detail")
        try:
            self._render_snapshot(self._controller.doctor())
        except Exception:
            self.query_one("#doctor-summary", Static).update("× Doctor load failed.")

    def _level_label(self, level: str) -> str:
        if level == "failed":
            return "Failed"
        if level == "warning":
            return "Warning"
        return "Passed"

    def _render_snapshot(self, snapshot: DoctorSnapshot) -> None:
        table = self.query_one("#doctor-table", DataTable)
        table.clear()
        if snapshot.load_error:
            self.query_one("#doctor-summary", Static).update(f"× {snapshot.load_error}")
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

        for group in group_order:
            for check in grouped.get(group, []):
                detail = check.detail
                if check.suggested_action:
                    detail = f"{detail} → {check.suggested_action}"
                table.add_row(
                    group,
                    self._level_label(check.level),
                    check.title,
                    detail,
                )
        if snapshot.has_errors:
            overall = "Overall: blocking issues found"
        else:
            overall = "Overall: no blocking errors"
        self.query_one("#doctor-summary", Static).update(f"Doctor\n{overall}")

    def run_doctor(self) -> None:
        self._active_token = self._begin_load()
        self.query_one("#btn-run-doctor", Button).disabled = True
        self.query_one("#doctor-summary", Static).update(
            loading_message("Running doctor...", "doctor")
        )
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
                self.query_one("#doctor-summary", Static).update(
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
        elif event.button.id == "btn-export-support":
            self._export_support_report()
        elif event.button.id == "btn-tech-log":
            from .logs_screen import TechnicalLogScreen

            self.app.push_screen(TechnicalLogScreen(self._controller))
        elif event.button.id == "btn-back":
            self.action_back()

    def _begin_export(self) -> int:
        self._export_generation += 1
        return self._export_generation

    def _is_current_export(self) -> bool:
        return self._export_started_token == self._export_token and self.is_mounted

    def _export_support_report(self) -> None:
        if self._export_in_progress:
            return
        self._export_in_progress = True
        self._export_token = self._begin_export()
        self._export_started_token = self._export_token
        self.query_one("#btn-export-support", Button).disabled = True
        self.query_one("#doctor-export-status", Static).update(
            loading_message("Exporting support report...", "support_export")
        )
        self._export_worker_handle = self.export_support_report_worker()
        self.set_interval(0.05, self._poll_export_worker, repeat=40)

    def _poll_export_worker(self) -> None:
        worker = getattr(self, "_export_worker_handle", None)
        if worker is None or worker.state is WorkerState.RUNNING:
            return
        self._finish_export_worker(worker)

    def _finish_export_worker(self, worker) -> None:
        if not self._export_in_progress:
            return
        self._export_in_progress = False
        if self.is_mounted:
            self.query_one("#btn-export-support", Button).disabled = False
        if worker.state is WorkerState.ERROR:
            if self.is_mounted:
                self.query_one("#doctor-export-status", Static).update(
                    "× Support report could not be exported."
                )
            self._export_worker_handle = None
            return
        if worker.state is not WorkerState.SUCCESS:
            self._export_worker_handle = None
            return
        if not self._is_current_export():
            self._export_worker_handle = None
            return
        export_result = worker.result
        self._export_worker_handle = None
        if not isinstance(export_result, ReportExportResult):
            return
        status = self.query_one("#doctor-export-status", Static)
        if export_result.ok and export_result.path is not None:
            redacted = redact_path(export_result.path) or export_result.path
            status.update(f"Report saved\n{redacted}")
            return
        status.update(f"× {export_result.message or 'Support report could not be exported.'}")

    @work(thread=True, exclusive=True, group="support-report-export")
    def export_support_report_worker(self) -> ReportExportResult:
        try:
            path = self._controller.export_support_report(fmt="json")
            return ReportExportResult(ok=True, path=str(path))
        except FileExistsError as exc:
            return ReportExportResult(ok=False, message=str(exc))
        except Exception:
            return ReportExportResult(
                ok=False,
                message="Support report could not be exported.",
            )

    def on_export_support_report_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state is WorkerState.RUNNING:
            return
        self._finish_export_worker(event.worker)

    def action_run_doctor(self) -> None:
        self.run_doctor()

    def action_back(self) -> None:
        self.app.pop_screen()
