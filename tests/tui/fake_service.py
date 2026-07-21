"""Shared TUI test helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from spell_sync.application.builders import (
    build_pull_operation_report,
    build_push_operation_report,
    build_recovery_operation_report,
    build_setup_operation_report,
    build_target_settings_operation_report,
)
from spell_sync.application.events import EventLevel, EventSink, OperationEvent, OperationKind
from spell_sync.application.reports import (
    DashboardIssue,
    DashboardSeverity,
    DashboardState,
    DoctorCheckView,
    DoctorSnapshot,
    OperationOutcome,
    PullExecution,
    PullPreview,
    PullSourcePreview,
    PushExecution,
    PushPreview,
    RecoveryExecution,
    RecoveryItemPreview,
    RecoveryOutcome,
    RecoveryPreview,
    RecoveryStatus,
    StatusDetailSnapshot,
    StatusSnapshot,
    TargetPreview,
    TargetStatusRow,
)
from spell_sync.application.requests import (
    DoctorRequest,
    PrepareTargetSettingsUpdateRequest,
    PullRequest,
    PushRequest,
    RecoveryRequest,
    SetupRequest,
    StatusRequest,
    TargetSettingsRequest,
)
from spell_sync.exit_codes import ExitCode
from spell_sync.project_setup.discovery import SetupTargetDiscovery, discover_setup_targets
from spell_sync.project_setup.draft import SetupDraft
from spell_sync.project_setup.execute import ProjectSetupExecution, ProjectSetupOutcome
from spell_sync.project_setup.prepare import PreparedProjectSetup, prepare_project_setup
from spell_sync.project_setup.state import ProjectSetupState, ProjectSetupStatus
from spell_sync.project_setup.target_settings import (
    PreparedTargetSettingsUpdate,
    TargetSettingsExecution,
    TargetSettingsOutcome,
    TargetSettingsSnapshot,
)
from spell_sync.push_prepared import PreparedPush
from spell_sync.sync_models import DictionaryDiff, PushResult


@dataclass
class FakeTuiService:
    dashboard_state: DashboardState
    status_snapshot: StatusSnapshot
    status_detail: StatusDetailSnapshot
    preview: PushPreview
    doctor: DoctorSnapshot
    pull_preview: PullPreview
    preview_counter: int = 0
    pull_counter: int = 0
    execute_push_calls: int = 0
    execute_pull_calls: int = 0
    last_executed_prepared: object | None = None
    push_execution: PushExecution | None = None
    pull_execution: PullExecution | None = None
    recovery_preview: RecoveryPreview | None = None
    recovery_execution: RecoveryExecution | None = None
    execute_recovery_calls: int = 0
    raise_on_execute: Exception | None = None
    raise_on_inspect: Exception | None = None
    setup_state: ProjectSetupState | None = None
    setup_prepared: PreparedProjectSetup | None = None
    setup_execution: ProjectSetupExecution | None = None
    execute_setup_calls: int = 0
    target_settings_snapshot: TargetSettingsSnapshot | None = None
    target_settings_prepared: PreparedTargetSettingsUpdate | None = None
    target_settings_execution: TargetSettingsExecution | None = None
    execute_target_settings_calls: int = 0

    def load_dashboard(self, request: StatusRequest) -> DashboardState:
        return self.dashboard_state

    def load_status(self, request: StatusRequest) -> StatusSnapshot:
        return self.status_snapshot

    def load_status_detail(self, request: StatusRequest) -> StatusDetailSnapshot:
        return self.status_detail

    def load_push_preview(self, request: PushRequest) -> PushPreview:
        self.preview_counter += 1
        if self.preview.prepared is not None:
            return replace(
                self.preview,
                plan_identifier=f"plan-{self.preview_counter}",
            )
        return self.preview

    def load_doctor(self, request: DoctorRequest) -> DoctorSnapshot:
        return self.doctor

    def prepare_pull(self, request: PullRequest) -> PullPreview:
        self.pull_counter += 1
        return replace(
            self.pull_preview,
            plan_identifier=f"pull-{self.pull_counter}",
        )

    def execute_pull(
        self,
        request: PullRequest,
        preview: PullPreview,
        *,
        confirmed_plan_id: str,
        event_sink: EventSink | None = None,
    ) -> PullExecution:
        self.execute_pull_calls += 1
        if self.raise_on_execute is not None:
            raise self.raise_on_execute
        if event_sink is not None:
            event_sink(
                OperationEvent(
                    OperationKind.PULL,
                    "acquiring_lock",
                    "Operation lock acquired",
                    level=EventLevel.SUCCESS,
                )
            )
            event_sink(
                OperationEvent(
                    OperationKind.PULL,
                    "writing_wordlist",
                    "Writing canonical wordlist",
                )
            )
            event_sink(
                OperationEvent(
                    OperationKind.PULL,
                    "completed",
                    "Pull completed",
                    level=EventLevel.SUCCESS,
                )
            )
        if self.pull_execution is not None:
            return self.pull_execution
        return PullExecution(
            preview=preview,
            result=(preview.before_count, preview.after_count),
            outcome=OperationOutcome.COMPLETED,
            message=f"added {preview.additions}",
            warnings=preview.warnings,
        )

    def execute_push_preview(
        self,
        request: PullRequest,
        preview: PushPreview,
        *,
        confirmed_plan_id: str,
        event_sink: EventSink | None = None,
    ) -> PushExecution:
        self.execute_push_calls += 1
        self.last_executed_prepared = preview.prepared
        if self.raise_on_execute is not None:
            raise self.raise_on_execute
        if event_sink is not None:
            event_sink(
                OperationEvent(
                    OperationKind.PUSH,
                    "acquiring_lock",
                    "Operation lock acquired",
                    level=EventLevel.SUCCESS,
                )
            )
            event_sink(
                OperationEvent(
                    OperationKind.PUSH,
                    "verifying_plan",
                    "Prepared plan verified",
                    level=EventLevel.SUCCESS,
                )
            )
            event_sink(
                OperationEvent(
                    OperationKind.PUSH,
                    "creating_snapshots",
                    "Creating recovery snapshots",
                    completed=0,
                    total=1,
                )
            )
            event_sink(
                OperationEvent(
                    OperationKind.PUSH,
                    "completed",
                    "Push completed",
                    level=EventLevel.SUCCESS,
                )
            )
        if self.push_execution is not None:
            return replace(
                self.push_execution,
                prepared=preview.prepared,
                plan_identifier=preview.plan_identifier,
                push_preview=preview,
            )
        return PushExecution(
            prepared=preview.prepared,
            result=PushResult(word_count=3, written=("chrome",)),
            outcome=OperationOutcome.COMPLETED,
            message="Updated targets: chrome",
            plan_identifier=preview.plan_identifier,
            push_preview=preview,
        )

    def build_push_report(self, execution: PushExecution):
        return build_push_operation_report(execution)

    def build_pull_report(self, execution: PullExecution):
        return build_pull_operation_report(execution)

    def inspect_recovery(self, request: RecoveryRequest) -> RecoveryPreview:
        if self.raise_on_inspect is not None:
            raise self.raise_on_inspect
        return self.recovery_preview or sample_recovery_preview()

    def execute_recovery(
        self,
        request: PullRequest,
        preview: RecoveryPreview,
        *,
        confirmed_transaction_id: str,
        event_sink: EventSink | None = None,
    ) -> RecoveryExecution:
        self.execute_recovery_calls += 1
        if self.raise_on_execute is not None:
            raise self.raise_on_execute
        if event_sink is not None:
            event_sink(
                OperationEvent(
                    OperationKind.RECOVER,
                    "validating_journal",
                    "Validating journal",
                    level=EventLevel.SUCCESS,
                )
            )
            event_sink(
                OperationEvent(
                    OperationKind.RECOVER,
                    "completed",
                    "Recovery completed",
                    level=EventLevel.SUCCESS,
                )
            )
        if self.recovery_execution is not None:
            return self.recovery_execution
        return RecoveryExecution(
            preview=preview,
            result=ExitCode.OK,
            outcome=RecoveryOutcome.RECOVERED,
            message="2 file(s) restored",
            restored=("wordlist", "chrome"),
        )

    def execute_recovery_cleanup(
        self,
        request: PullRequest,
        preview: RecoveryPreview,
        *,
        confirmed_transaction_id: str,
        event_sink: EventSink | None = None,
    ) -> RecoveryExecution:
        return RecoveryExecution(
            preview=preview,
            result=ExitCode.OK,
            outcome=RecoveryOutcome.CLEANUP_COMPLETED,
            message="Remaining recovery artifacts were removed.",
        )

    def execute_recovery_discard(
        self,
        request: PullRequest,
        preview: RecoveryPreview,
        *,
        confirmed_transaction_id: str,
        event_sink: EventSink | None = None,
    ) -> RecoveryExecution:
        return RecoveryExecution(
            preview=preview,
            result=ExitCode.OK,
            outcome=RecoveryOutcome.DISCARDED,
            message="Recovery metadata discarded.",
        )

    def build_recovery_report(self, execution: RecoveryExecution):
        return build_recovery_operation_report(execution)

    def inspect_project_setup(self, request: SetupRequest) -> ProjectSetupState:
        if self.setup_state is not None:
            return self.setup_state
        return ProjectSetupState(
            status=ProjectSetupStatus.READY,
            effective_wordlist=None,
            project_dir=None,
            config_path=None,
            can_start_wizard=False,
            detail=None,
        )

    def discover_setup_targets(self, draft: SetupDraft) -> SetupTargetDiscovery:
        return discover_setup_targets(selected_targets=draft.selected_targets)

    def prepare_project_setup(self, draft: SetupDraft) -> PreparedProjectSetup:
        if self.setup_prepared is not None:
            return self.setup_prepared
        return prepare_project_setup(draft)

    def execute_project_setup(
        self,
        prepared: PreparedProjectSetup,
        *,
        confirmed_setup_id: str,
        event_sink=None,
    ) -> ProjectSetupExecution:
        self.execute_setup_calls += 1
        if self.raise_on_execute is not None:
            raise self.raise_on_execute
        if self.setup_execution is not None:
            return self.setup_execution
        return ProjectSetupExecution(
            prepared=prepared,
            outcome=ProjectSetupOutcome.COMPLETED,
            message="Project created.",
            created_files=tuple(
                item.relative_name for item in prepared.files if item.action.value == "create"
            ),
        )

    def validate_setup_wordlist(self, raw_path: str):
        from spell_sync.project_setup.state import validate_setup_wordlist

        return validate_setup_wordlist(raw_path)

    def build_setup_report(self, execution: ProjectSetupExecution):
        return build_setup_operation_report(execution)

    def load_target_settings(self, request: TargetSettingsRequest) -> TargetSettingsSnapshot:
        if self.target_settings_snapshot is not None:
            return self.target_settings_snapshot
        return TargetSettingsSnapshot(
            config_path=Path("/tmp/project/spell-sync.toml"),
            wordlist_path=Path("/tmp/project/wordlist.txt"),
            targets=(),
            enabled_target_ids=frozenset(),
        )

    def prepare_target_settings_update(
        self,
        request: PrepareTargetSettingsUpdateRequest,
    ) -> PreparedTargetSettingsUpdate:
        selected_target_ids = request.selected_target_ids
        if self.target_settings_prepared is not None:
            return self.target_settings_prepared
        return PreparedTargetSettingsUpdate(
            update_id="target-update-1",
            config_path=Path("/tmp/project/spell-sync.toml"),
            wordlist_path=Path("/tmp/project/wordlist.txt"),
            selected_target_ids=selected_target_ids,
            previous_target_ids=frozenset({"chrome"}),
            enabled_target_ids=frozenset({"edge"}),
            disabled_target_ids=frozenset(),
            rendered_config_bytes=b"[dictionaries]\n",
            config_fingerprint_before="abc",
            warnings=(),
            can_execute=True,
        )

    def execute_target_settings_update(
        self,
        prepared: PreparedTargetSettingsUpdate,
        *,
        confirmed_update_id: str,
        event_sink: EventSink | None = None,
    ) -> TargetSettingsExecution:
        self.execute_target_settings_calls += 1
        if self.raise_on_execute is not None:
            raise self.raise_on_execute
        if event_sink is not None:
            event_sink(
                OperationEvent(
                    OperationKind.TARGETS,
                    "completed",
                    "Configuration updated",
                    level=EventLevel.SUCCESS,
                )
            )
        if self.target_settings_execution is not None:
            return self.target_settings_execution
        return TargetSettingsExecution(
            prepared=prepared,
            outcome=TargetSettingsOutcome.COMPLETED,
            message="Enabled: Edge",
        )

    def build_target_settings_report(self, execution: TargetSettingsExecution):
        return build_target_settings_operation_report(execution)

    def load_operation_history(self, **kwargs):
        from spell_sync.diagnostics.types import OperationHistorySnapshot

        return OperationHistorySnapshot(records=())

    def clear_operation_history(self):
        from spell_sync.diagnostics.types import HistoryClearResult

        return HistoryClearResult(ok=True)

    def technical_log_path(self):
        from pathlib import Path

        return Path("/tmp/spell-sync-test.log")

    def read_technical_log_tail(self, **kwargs):
        from spell_sync.diagnostics.types import TechnicalLogSnapshot

        return TechnicalLogSnapshot(path=self.technical_log_path(), lines=())


def sample_recovery_preview(**kwargs) -> RecoveryPreview:
    defaults = dict(
        status=RecoveryStatus.RECOVERABLE,
        transaction_id="tx-12345678",
        command="push",
        transaction_state="writing",
        started_at="2026-01-01T00:00:00+00:00",
        wordlist_path="/tmp/wordlist.txt",
        snapshot_directory="/tmp/snapshots",
        items=(
            RecoveryItemPreview(
                name="wordlist",
                path="/tmp/wordlist.txt",
                current_state="Post-write",
                recovery_action="Restore snapshot",
                status="ready",
            ),
        ),
        recoverable_count=1,
        conflict_count=0,
        failure_count=0,
        warnings=(),
        can_recover=True,
        can_discard=False,
        snapshots_valid=True,
        preview_fingerprint="tx-12345678",
    )
    defaults.update(kwargs)
    return RecoveryPreview(**defaults)


def sample_status(*, empty: bool = False, wordlist_error: ExitCode | None = None) -> StatusSnapshot:
    return StatusSnapshot(
        wordlist_count=0 if empty else 3,
        diffs=(
            DictionaryDiff(
                name="chrome",
                target_count=3,
                local_count=5,
                to_add=0,
                to_remove=2,
            ),
        )
        if not empty and wordlist_error is None
        else (),
        skipped_unreadable=(),
        skipped_corrupt=(),
        wordlist_error=wordlist_error,
        empty_wordlist=empty,
    )


def sample_status_detail(**kwargs) -> StatusDetailSnapshot:
    defaults = dict(
        wordlist_path="/tmp/wordlist.txt",
        project_dir="/tmp",
        config_paths=("/tmp/spell-sync.toml",),
        wordlist_count=3,
        targets=(
            TargetStatusRow(
                name="chrome",
                enabled=True,
                available=True,
                read_status="ok",
                path="/tmp/chrome.txt",
                format="chrome",
                word_count=5,
            ),
        ),
        skipped_unreadable=(),
        skipped_corrupt=(),
    )
    defaults.update(kwargs)
    return StatusDetailSnapshot(**defaults)


def sample_dashboard(**kwargs) -> DashboardState:
    snapshot = kwargs.pop("snapshot", sample_status())
    defaults = dict(
        wordlist_path="/tmp/wordlist.txt",
        project_dir="/tmp",
        config_status="valid",
        config_valid=True,
        targets_detected=2,
        targets_enabled=2,
        targets_available=2,
        targets_ready=2,
        targets_needs_attention=0,
        targets_disabled=0,
        targets_unavailable=0,
        pending_recovery=False,
        overall_severity=DashboardSeverity.READY,
        overall_label="✓ Ready",
        issues=(),
        snapshot=snapshot,
        last_operation_summary=None,
    )
    defaults.update(kwargs)
    return DashboardState(**defaults)


def _fake_prepared() -> PreparedPush:
    from unittest.mock import MagicMock

    planned = MagicMock()
    planned.dictionary.name = "chrome"
    planned.additions = frozenset({"a", "b"})
    planned.removals = frozenset({"x"})
    target = MagicMock()
    target.planned = planned
    plan = MagicMock()
    ctx = MagicMock()
    ctx.wordlist_str = "/tmp/wordlist.txt"
    identity = MagicMock()
    return PreparedPush(
        ctx=ctx,
        runtime_identity=identity,
        plan=plan,
        targets=(target,),
        dictionaries=(),
        skipped_unreadable=(),
        skipped_corrupt=(),
        skipped_blocked=(),
        wordlist_rendered=None,
        wordlist_needs_write=False,
    )


def sample_preview(**kwargs) -> PushPreview:
    defaults = dict(
        prepared=_fake_prepared(),
        targets=(
            TargetPreview(
                name="chrome",
                additions=2,
                removals=1,
                status="Review",
                removal_words=frozenset({"x"}),
            ),
        ),
        additions=2,
        removals=1,
        warnings=(),
        created_at="2026-01-01T00:00:00+00:00",
        plan_identifier="abc12345",
        targets_to_update=1,
        unchanged=0,
        skipped=(),
        corrupt=(),
        blocked=(),
    )
    defaults.update(kwargs)
    return PushPreview(**defaults)


def sample_pull_preview(**kwargs) -> PullPreview:
    defaults = dict(
        wordlist_path="/tmp/wordlist.txt",
        additions=17,
        before_count=10,
        after_count=27,
        sources_used=("chrome", "cursor"),
        sources_skipped=("offline",),
        source_rows=(
            PullSourcePreview("chrome", "used", 10),
            PullSourcePreview("cursor", "used", 7),
            PullSourcePreview("offline", "skipped", detail="no access"),
        ),
        warnings=("Skipped unreadable: offline",),
        created_at="2026-01-01T00:00:00+00:00",
        plan_identifier="pull-1",
        merged_words=tuple(f"w{i}" for i in range(27)),
        addition_words=frozenset(f"new{i}" for i in range(17)),
        wordlist_fingerprint="deadbeef",
    )
    defaults.update(kwargs)
    return PullPreview(**defaults)


def sample_doctor(**kwargs) -> DoctorSnapshot:
    defaults = dict(
        checks=(
            DoctorCheckView(
                group="Project",
                level="passed",
                title="CLI available",
                detail="spell-sync is on PATH.",
            ),
        ),
        has_errors=False,
    )
    defaults.update(kwargs)
    return DoctorSnapshot(**defaults)


def fake_service(
    *,
    severity: DashboardSeverity = DashboardSeverity.READY,
    issues: tuple[DashboardIssue, ...] = (),
    wordlist_error: ExitCode | None = None,
    config_valid: bool = True,
    pending_recovery: bool = False,
    preview: PushPreview | None = None,
    pull_preview: PullPreview | None = None,
    status_detail: StatusDetailSnapshot | None = None,
    doctor: DoctorSnapshot | None = None,
    push_execution: PushExecution | None = None,
    pull_execution: PullExecution | None = None,
    recovery_preview: RecoveryPreview | None = None,
    recovery_execution: RecoveryExecution | None = None,
    setup_state: ProjectSetupState | None = None,
    targets_ready: int = 2,
    targets_needs_attention: int = 0,
    targets_disabled: int = 0,
    targets_unavailable: int = 0,
    last_operation_summary: str | None = None,
) -> FakeTuiService:
    snapshot = sample_status(wordlist_error=wordlist_error)
    labels = {
        DashboardSeverity.READY: "✓ Ready",
        DashboardSeverity.WARNING: "! Attention required",
        DashboardSeverity.BLOCKED: "× Writes blocked",
    }
    dashboard = sample_dashboard(
        config_valid=config_valid,
        pending_recovery=pending_recovery,
        overall_severity=severity,
        overall_label=labels[severity],
        issues=issues,
        snapshot=snapshot,
        targets_ready=targets_ready,
        targets_needs_attention=targets_needs_attention,
        targets_disabled=targets_disabled,
        targets_unavailable=targets_unavailable,
        last_operation_summary=last_operation_summary,
    )
    return FakeTuiService(
        dashboard,
        snapshot,
        status_detail or sample_status_detail(wordlist_error=wordlist_error),
        preview or sample_preview(),
        doctor or sample_doctor(),
        pull_preview or sample_pull_preview(),
        recovery_preview=recovery_preview,
        push_execution=push_execution,
        pull_execution=pull_execution,
        recovery_execution=recovery_execution,
        setup_state=setup_state,
    )
