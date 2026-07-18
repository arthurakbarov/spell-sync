"""Shared mutating operation progress screen for Pull and Push."""

from __future__ import annotations

import threading
from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Button, Footer, Header, ProgressBar, Static
from textual.worker import WorkerState

from ...application.events import EventLevel, OperationEvent
from ...application.reports import (
    OperationOutcome,
    OperationPhase,
    OperationReport,
    PullExecution,
    PullPreview,
    PushExecution,
    PushPreview,
    RecoveryExecution,
    RecoveryPreview,
)
from ...project_setup.execute import ProjectSetupExecution
from ...project_setup.prepare import PreparedProjectSetup
from ..controller import TuiController
from ..workers import LoadTokenMixin

_CANCELLATION_POLICY = (
    "Active write operations cannot be cancelled safely. "
    "The operation must finish or roll back before the screen can close."
)


class OperationScreen(LoadTokenMixin, Screen[None]):
    BINDINGS = [
        ("escape", "safe_back", "Back"),
        ("q", "safe_quit", "Quit"),
    ]

    phase: reactive[OperationPhase] = reactive(OperationPhase.PREPARING)

    def __init__(
        self,
        controller: TuiController,
        *,
        operation: str,
        pull_preview: PullPreview | None = None,
        push_preview: PushPreview | None = None,
        recovery_preview: RecoveryPreview | None = None,
        setup_prepared: PreparedProjectSetup | None = None,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._operation = operation
        self._pull_preview = pull_preview
        self._push_preview = push_preview
        self._recovery_preview = recovery_preview
        self._setup_prepared = setup_prepared
        self._events: list[OperationEvent] = []
        self._events_lock = threading.Lock()
        self._stage_lines: list[str] = []
        self._finished = False
        self._mutating = False
        self._active_token = 0
        self._report: OperationReport | None = None
        self._flush_timer: Timer | None = None
        self._worker: Any = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="operation-title")
        yield Static(id="operation-stages")
        yield ProgressBar(id="operation-progress", total=100, show_eta=False)
        yield Static(id="operation-details")
        yield Button("Close", id="btn-close", disabled=True)
        yield Footer()

    def on_mount(self) -> None:
        titles = {
            "setup": "Creating Spell Sync project",
            "pull": "Running pull",
            "push": "Running push",
            "recover": "Running recovery",
            "cleanup": "Running cleanup",
            "discard": "Running discard",
        }
        title = titles.get(self._operation, f"Running {self._operation}")
        self.query_one("#operation-title", Static).update(title)
        self.query_one("#operation-stages", Static).update("Preparing...")
        self.query_one("#operation-details", Static).update("")
        if not self._controller.begin_mutation():
            self.query_one("#operation-stages", Static).update(
                "× Another operation is already running."
            )
            self._finished = True
            self.query_one("#btn-close", Button).disabled = False
            return
        # Flush events on the UI thread; workers must not call_from_thread (deadlock).
        self._flush_timer = self.set_interval(0.05, self._poll_operation)
        self._active_token = self._begin_load()
        self._worker = self.execute_operation_worker()

    def on_unmount(self) -> None:
        if self._flush_timer is not None:
            self._flush_timer.stop()
        if not self._finished:
            self._controller.end_mutation()

    def _sink(self, event: OperationEvent) -> None:
        # Thread-safe append only; UI reads via interval flush.
        with self._events_lock:
            self._events.append(event)

    def _flush_events(self) -> None:
        if not self.is_mounted:
            return
        with self._events_lock:
            if not self._events:
                return
            pending = self._events[:]
            self._events.clear()
        for event in pending:
            self._apply_event(event)

    def _poll_operation(self) -> None:
        self._flush_events()
        if self._finished:
            return
        worker = getattr(self, "_worker", None)
        if worker is None:
            return
        if worker.state is WorkerState.ERROR:
            self._finish_failed("Operation failed unexpectedly.")
            return
        if worker.state is WorkerState.SUCCESS:
            self._complete_with_result(worker.result)

    def _apply_event(self, event: OperationEvent) -> None:
        if event.stage in {
            "acquiring_lock",
            "verifying_plan",
            "creating_snapshots",
            "validating_journal",
            "validating_snapshots",
            "checking_conflicts",
            "restoring_wordlist",
            "restoring_target",
            "removing_created_target",
        }:
            self._mutating = True
            self.phase = OperationPhase.EXECUTING
        if event.stage == "rolling_back":
            self.phase = OperationPhase.ROLLING_BACK
        if event.stage == "finalizing":
            self.phase = OperationPhase.FINALIZING
        prefix = {
            EventLevel.SUCCESS: "✓",
            EventLevel.WARNING: "!",
            EventLevel.ERROR: "×",
            EventLevel.INFO: "→",
        }[event.level]
        line = f"{prefix} {event.message}"
        if event.target:
            line = f"{prefix} {event.message} ({event.target})"
        self._stage_lines.append(line)
        self.query_one("#operation-stages", Static).update("\n".join(self._stage_lines[-12:]))
        if event.completed is not None and event.total:
            progress = self.query_one("#operation-progress", ProgressBar)
            progress.update(total=event.total, progress=event.completed)

    @work(thread=True, exclusive=True, group="mutation-execute")
    def execute_operation_worker(self):
        if self._operation == "pull" and self._pull_preview is not None:
            return self._controller.execute_pull(self._pull_preview, event_sink=self._sink)
        if self._operation == "push" and self._push_preview is not None:
            return self._controller.execute_push(self._push_preview, event_sink=self._sink)
        if self._operation == "recover" and self._recovery_preview is not None:
            return self._controller.execute_recovery(
                self._recovery_preview,
                event_sink=self._sink,
            )
        if self._operation == "cleanup" and self._recovery_preview is not None:
            return self._controller.execute_recovery_cleanup(
                self._recovery_preview,
                event_sink=self._sink,
            )
        if self._operation == "discard" and self._recovery_preview is not None:
            return self._controller.execute_recovery_discard(
                self._recovery_preview,
                event_sink=self._sink,
            )
        if self._operation == "setup" and self._setup_prepared is not None:
            return self._controller.execute_setup(
                self._setup_prepared,
                event_sink=self._sink,
            )
        return None

    def on_execute_operation_worker_state_changed(self, event) -> None:
        if event.state is WorkerState.RUNNING:
            return
        self._flush_events()
        if event.state is WorkerState.ERROR:
            self._finish_failed("Operation failed unexpectedly.")
        elif event.state is WorkerState.SUCCESS:
            self._complete_with_result(event.worker.result)

    def _complete_with_result(self, result) -> None:
        if self._finished:
            return
        # Mutation screen owns a single exclusive worker; ignore only if unmounted.
        if not self.is_mounted:
            return
        if isinstance(result, PullExecution):
            report = self._controller.pull_report(result)
        elif isinstance(result, PushExecution):
            report = self._controller.push_report(result)
        elif isinstance(result, RecoveryExecution):
            report = self._controller.recovery_report(result)
        elif isinstance(result, ProjectSetupExecution):
            report = self._controller.setup_report(result)
        else:
            self._finish_failed("Operation returned no result.")
            return
        self._report = report
        if report.outcome in {
            OperationOutcome.COMPLETED,
            OperationOutcome.COMPLETED_WITH_WARNINGS,
        }:
            self.phase = OperationPhase.COMPLETED
        else:
            self.phase = OperationPhase.FAILED
        self._finished = True
        self._mutating = False
        self._controller.end_mutation()
        self._controller.invalidate_pull_preview()
        self._controller.invalidate_push_preview()
        self._controller.invalidate_recovery_preview()
        if self._flush_timer is not None:
            self._flush_timer.stop()
        from .report_screen import ReportScreen

        self.app.push_screen(ReportScreen(self._controller, report))

    def _finish_failed(self, message: str) -> None:
        self.phase = OperationPhase.FAILED
        self._finished = True
        self._mutating = False
        self._controller.end_mutation()
        if self.is_mounted:
            self.query_one("#operation-stages", Static).update(f"× {message}")
            self.query_one("#btn-close", Button).disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-close" and self._finished:
            self.app.pop_screen()

    def action_safe_back(self) -> None:
        if self._mutating and not self._finished:
            self.notify(_CANCELLATION_POLICY, severity="warning")
            return
        if self._finished:
            self.app.pop_screen()

    def action_safe_quit(self) -> None:
        if self._mutating and not self._finished:
            self.notify(_CANCELLATION_POLICY, severity="warning")
            return
        self.app.exit(0)
