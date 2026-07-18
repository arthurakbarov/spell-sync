"""TUI controller over the application service."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Protocol

from ..application.events import EventSink, OperationKind
from ..application.reports import (
    DashboardState,
    DoctorSnapshot,
    OperationOutcome,
    OperationReport,
    PullExecution,
    PullPreview,
    PushExecution,
    PushPreview,
    RecoveryExecution,
    RecoveryPreview,
    StatusDetailSnapshot,
    StatusSnapshot,
)
from ..cli_options import CliOptions
from ..project_setup.discovery import SetupTargetDiscovery
from ..project_setup.draft import SetupDraft
from ..project_setup.execute import ProjectSetupExecution
from ..project_setup.prepare import PreparedProjectSetup
from ..project_setup.selection import (
    SetupSelection,
    clear_selectable_targets,
    default_selection,
    merge_selection_after_refresh,
    select_available_targets,
    selection_tuple,
    toggle_target,
)
from ..project_setup.state import ProjectSetupState


class TuiService(Protocol):
    def load_dashboard(self, opts: CliOptions) -> DashboardState: ...

    def load_status(self, opts: CliOptions) -> StatusSnapshot: ...

    def load_status_detail(self, opts: CliOptions) -> StatusDetailSnapshot: ...

    def load_push_preview(self, opts: CliOptions) -> PushPreview: ...

    def load_doctor(self, opts: CliOptions) -> DoctorSnapshot: ...

    def prepare_pull(self, opts: CliOptions) -> PullPreview: ...

    def execute_pull(
        self,
        opts: CliOptions,
        preview: PullPreview,
        *,
        confirmed_plan_id: str,
        event_sink: EventSink | None = None,
    ) -> PullExecution: ...

    def execute_push_preview(
        self,
        opts: CliOptions,
        preview: PushPreview,
        *,
        confirmed_plan_id: str,
        event_sink: EventSink | None = None,
    ) -> PushExecution: ...

    def build_push_report(self, execution: PushExecution) -> OperationReport: ...

    def build_pull_report(self, execution: PullExecution) -> OperationReport: ...

    def inspect_recovery(self, opts: CliOptions) -> RecoveryPreview: ...

    def execute_recovery(
        self,
        opts: CliOptions,
        preview: RecoveryPreview,
        *,
        confirmed_transaction_id: str,
        event_sink: EventSink | None = None,
    ) -> RecoveryExecution: ...

    def execute_recovery_cleanup(
        self,
        opts: CliOptions,
        preview: RecoveryPreview,
        *,
        confirmed_transaction_id: str,
        event_sink: EventSink | None = None,
    ) -> RecoveryExecution: ...

    def execute_recovery_discard(
        self,
        opts: CliOptions,
        preview: RecoveryPreview,
        *,
        confirmed_transaction_id: str,
        event_sink: EventSink | None = None,
    ) -> RecoveryExecution: ...

    def build_recovery_report(self, execution: RecoveryExecution) -> OperationReport: ...

    def inspect_project_setup(self, opts: CliOptions) -> ProjectSetupState: ...

    def discover_setup_targets(self, draft: SetupDraft) -> SetupTargetDiscovery: ...

    def prepare_project_setup(self, draft: SetupDraft) -> PreparedProjectSetup: ...

    def execute_project_setup(
        self,
        prepared: PreparedProjectSetup,
        *,
        confirmed_setup_id: str,
        event_sink: EventSink | None = None,
    ) -> ProjectSetupExecution: ...

    def validate_setup_wordlist(self, raw_path: str) -> tuple[Path, str | None]: ...

    def build_setup_report(self, execution: ProjectSetupExecution) -> OperationReport: ...

    def load_operation_history(
        self,
        *,
        limit: int = 50,
        operation: OperationKind | None = None,
        outcome: OperationOutcome | None = None,
    ): ...

    def clear_operation_history(self): ...

    def technical_log_path(self) -> Path: ...

    def read_technical_log_tail(
        self,
        *,
        max_lines: int = 200,
        max_bytes: int = 128 * 1024,
    ): ...


class TuiController:
    def __init__(self, service: TuiService, opts: CliOptions) -> None:
        self._service = service
        self.opts = opts
        self._mutation_active = False
        self._active_push_preview: PushPreview | None = None
        self._active_pull_preview: PullPreview | None = None
        self._active_recovery_preview: RecoveryPreview | None = None
        self._setup_wordlist: Path | None = None
        self._setup_discovery: SetupTargetDiscovery | None = None
        self._setup_selection: SetupSelection | None = None
        self._setup_prepared: PreparedProjectSetup | None = None

    @property
    def setup_selected_targets(self) -> tuple[str, ...]:
        if self._setup_selection is None:
            return ()
        return selection_tuple(self._setup_selection)

    def setup_selection(self) -> SetupSelection:
        if self._setup_selection is None:
            return SetupSelection(frozenset())
        return self._setup_selection

    def setup_target_discovery(self) -> SetupTargetDiscovery:
        if self._setup_discovery is None:
            raise RuntimeError("Setup target discovery is not available.")
        return self._setup_discovery

    @property
    def mutation_active(self) -> bool:
        return self._mutation_active

    def begin_mutation(self) -> bool:
        if self._mutation_active:
            return False
        self._mutation_active = True
        return True

    def end_mutation(self) -> None:
        self._mutation_active = False

    def dashboard(self) -> DashboardState:
        return self._service.load_dashboard(self.opts)

    def status(self) -> StatusSnapshot:
        return self._service.load_status(self.opts)

    def status_detail(self) -> StatusDetailSnapshot:
        return self._service.load_status_detail(self.opts)

    def preview(self) -> PushPreview:
        preview = self._service.load_push_preview(self.opts)
        self._active_push_preview = preview
        return preview

    def invalidate_push_preview(self) -> None:
        self._active_push_preview = None

    def active_push_preview(self) -> PushPreview | None:
        return self._active_push_preview

    def doctor(self) -> DoctorSnapshot:
        return self._service.load_doctor(self.opts)

    def prepare_pull(self) -> PullPreview:
        preview = self._service.prepare_pull(self.opts)
        self._active_pull_preview = preview
        return preview

    def invalidate_pull_preview(self) -> None:
        self._active_pull_preview = None

    def active_pull_preview(self) -> PullPreview | None:
        return self._active_pull_preview

    def execute_pull(
        self,
        preview: PullPreview,
        *,
        event_sink: EventSink | None = None,
    ) -> PullExecution:
        return self._service.execute_pull(
            self.opts,
            preview,
            confirmed_plan_id=preview.plan_identifier,
            event_sink=event_sink,
        )

    def execute_push(
        self,
        preview: PushPreview,
        *,
        event_sink: EventSink | None = None,
    ) -> PushExecution:
        # Identity: must use this preview's prepared plan, never re-prepare.
        return self._service.execute_push_preview(
            self.opts,
            preview,
            confirmed_plan_id=preview.plan_identifier,
            event_sink=event_sink,
        )

    def push_report(self, execution: PushExecution) -> OperationReport:
        return self._service.build_push_report(execution)

    def pull_report(self, execution: PullExecution) -> OperationReport:
        return self._service.build_pull_report(execution)

    def inspect_recovery(self) -> RecoveryPreview:
        preview = self._service.inspect_recovery(self.opts)
        self._active_recovery_preview = preview
        return preview

    def set_active_recovery_preview(self, preview: RecoveryPreview) -> None:
        self._active_recovery_preview = preview

    def invalidate_recovery_preview(self) -> None:
        self._active_recovery_preview = None

    def active_recovery_preview(self) -> RecoveryPreview | None:
        return self._active_recovery_preview

    def execute_recovery(
        self,
        preview: RecoveryPreview,
        *,
        event_sink: EventSink | None = None,
    ) -> RecoveryExecution:
        return self._service.execute_recovery(
            self.opts,
            preview,
            confirmed_transaction_id=preview.preview_fingerprint,
            event_sink=event_sink,
        )

    def execute_recovery_cleanup(
        self,
        preview: RecoveryPreview,
        *,
        event_sink: EventSink | None = None,
    ) -> RecoveryExecution:
        return self._service.execute_recovery_cleanup(
            self.opts,
            preview,
            confirmed_transaction_id=preview.preview_fingerprint,
            event_sink=event_sink,
        )

    def execute_recovery_discard(
        self,
        preview: RecoveryPreview,
        *,
        event_sink: EventSink | None = None,
    ) -> RecoveryExecution:
        return self._service.execute_recovery_discard(
            self.opts,
            preview,
            confirmed_transaction_id=preview.preview_fingerprint,
            event_sink=event_sink,
        )

    def recovery_report(self, execution: RecoveryExecution) -> OperationReport:
        return self._service.build_recovery_report(execution)

    def load_operation_history(
        self,
        *,
        limit: int = 50,
        operation: OperationKind | None = None,
        outcome: OperationOutcome | None = None,
    ):
        return self._service.load_operation_history(
            limit=limit,
            operation=operation,
            outcome=outcome,
        )

    def clear_operation_history(self):
        return self._service.clear_operation_history()

    def technical_log_path(self) -> Path:
        return self._service.technical_log_path()

    def read_technical_log_tail(self, **kwargs):
        return self._service.read_technical_log_tail(**kwargs)

    def writes_blocked(self, state: DashboardState | None = None) -> bool:
        current = state or self.dashboard()
        return current.pending_recovery or current.overall_severity.value == "blocked"

    def inspect_project_setup(self) -> ProjectSetupState:
        return self._service.inspect_project_setup(self.opts)

    def setup_wordlist_default(self) -> Path:
        return Path.home() / "spell-words" / "wordlist.txt"

    def validate_setup_wordlist(self, raw_path: str) -> tuple[Path, str | None]:
        return self._service.validate_setup_wordlist(raw_path)

    def set_setup_wordlist(self, path: Path) -> None:
        wordlist_changed = self._setup_wordlist != path
        self._setup_wordlist = path
        self._load_setup_discovery(reset_selection=wordlist_changed)

    def _load_setup_discovery(self, *, reset_selection: bool) -> None:
        if self._setup_wordlist is None:
            return
        draft = SetupDraft(
            self._setup_wordlist,
            (),
            create_wordlist=not self._setup_wordlist.is_file(),
        )
        discovery = self._service.discover_setup_targets(draft)
        self._setup_discovery = discovery
        if reset_selection or self._setup_selection is None:
            self._setup_selection = default_selection(discovery)
        else:
            previous_ids = frozenset(
                target.identifier
                for target in (self._setup_discovery.targets if self._setup_discovery else ())
            )
            self._setup_selection = merge_selection_after_refresh(
                self._setup_selection,
                previous_ids,
                discovery,
            )

    def refresh_setup_target_discovery(self) -> SetupTargetDiscovery:
        draft = self._setup_draft()
        previous_discovery = self._setup_discovery
        previous_ids = (
            frozenset(target.identifier for target in previous_discovery.targets)
            if previous_discovery
            else frozenset()
        )
        previous_selection = self._setup_selection or SetupSelection(frozenset())
        discovery = self._service.discover_setup_targets(draft)
        self._setup_discovery = discovery
        self._setup_selection = merge_selection_after_refresh(
            previous_selection,
            previous_ids,
            discovery,
        )
        self._setup_prepared = None
        return discovery

    def toggle_setup_target(self, target_id: str) -> bool:
        if self._setup_discovery is None or self._setup_selection is None:
            return False
        updated = toggle_target(self._setup_selection, self._setup_discovery, target_id)
        if updated == self._setup_selection:
            return False
        self._setup_selection = updated
        self._setup_prepared = None
        return True

    def select_available_setup_targets(self) -> None:
        if self._setup_discovery is None or self._setup_selection is None:
            return
        self._setup_selection = select_available_targets(
            self._setup_selection,
            self._setup_discovery,
        )
        self._setup_prepared = None

    def clear_setup_target_selection(self) -> None:
        if self._setup_discovery is None or self._setup_selection is None:
            return
        self._setup_selection = clear_selectable_targets(
            self._setup_selection,
            self._setup_discovery,
        )
        self._setup_prepared = None

    def refresh_setup_targets(self) -> SetupTargetDiscovery:
        return self.refresh_setup_target_discovery()

    def prepare_setup_preview(self) -> PreparedProjectSetup:
        prepared = self._service.prepare_project_setup(self._setup_draft())
        self._setup_prepared = prepared
        return prepared

    def execute_setup(
        self,
        prepared: PreparedProjectSetup,
        *,
        event_sink: EventSink | None = None,
    ) -> ProjectSetupExecution:
        execution = self._service.execute_project_setup(
            prepared,
            confirmed_setup_id=prepared.setup_id,
            event_sink=event_sink,
        )
        if execution.outcome.value == "completed":
            self.opts = replace(self.opts, wordlist=str(prepared.wordlist_path))
            self.clear_setup_session()
        return execution

    def setup_report(self, execution: ProjectSetupExecution) -> OperationReport:
        return self._service.build_setup_report(execution)

    def clear_setup_session(self) -> None:
        self._setup_wordlist = None
        self._setup_discovery = None
        self._setup_selection = None
        self._setup_prepared = None

    def _setup_draft(self) -> SetupDraft:
        if self._setup_wordlist is None:
            raise RuntimeError("Setup wordlist is not selected.")
        return SetupDraft(
            wordlist_path=self._setup_wordlist,
            selected_targets=self.setup_selected_targets,
            create_wordlist=not self._setup_wordlist.is_file(),
        )
