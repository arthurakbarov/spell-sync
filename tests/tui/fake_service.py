"""Shared TUI test helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace

from spell_sync.application.builders import (
    build_pull_operation_report,
    build_push_operation_report,
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
    StatusDetailSnapshot,
    StatusSnapshot,
    TargetPreview,
    TargetStatusRow,
)
from spell_sync.cli_options import CliOptions
from spell_sync.exit_codes import ExitCode
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
    raise_on_execute: Exception | None = None

    def load_dashboard(self, opts: CliOptions) -> DashboardState:
        return self.dashboard_state

    def load_status(self, opts: CliOptions) -> StatusSnapshot:
        return self.status_snapshot

    def load_status_detail(self, opts: CliOptions) -> StatusDetailSnapshot:
        return self.status_detail

    def load_push_preview(self, opts: CliOptions) -> PushPreview:
        self.preview_counter += 1
        if self.preview.prepared is not None:
            return replace(
                self.preview,
                plan_identifier=f"plan-{self.preview_counter}",
            )
        return self.preview

    def load_doctor(self, opts: CliOptions) -> DoctorSnapshot:
        return self.doctor

    def prepare_pull(self, opts: CliOptions) -> PullPreview:
        self.pull_counter += 1
        return replace(
            self.pull_preview,
            plan_identifier=f"pull-{self.pull_counter}",
        )

    def execute_pull(
        self,
        opts: CliOptions,
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
        opts: CliOptions,
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
            )
        return PushExecution(
            prepared=preview.prepared,
            result=PushResult(word_count=3, written=("chrome",)),
            outcome=OperationOutcome.COMPLETED,
            message="Updated targets: chrome",
            plan_identifier=preview.plan_identifier,
        )

    def build_push_report(self, execution: PushExecution):
        return build_push_operation_report(execution)

    def build_pull_report(self, execution: PullExecution):
        return build_pull_operation_report(execution)


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
        pending_recovery=False,
        overall_severity=DashboardSeverity.READY,
        overall_label="✓ Ready",
        issues=(),
        snapshot=snapshot,
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
    return PreparedPush(
        ctx=ctx,
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
    )
    return FakeTuiService(
        dashboard,
        snapshot,
        status_detail or sample_status_detail(wordlist_error=wordlist_error),
        preview or sample_preview(),
        doctor or sample_doctor(),
        pull_preview or sample_pull_preview(),
        push_execution=push_execution,
        pull_execution=pull_execution,
    )
