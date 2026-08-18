"""Structured application results shared by CLI and TUI."""

from dataclasses import dataclass, field
from enum import StrEnum

from .exit_codes import ExitCode
from .push_prepared import PreparedPush
from .runtime_identity import RuntimeIdentity
from .sync_models import DictionaryDiff, PushResult


class DashboardSeverity(StrEnum):
    READY = "ready"
    WARNING = "warning"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class DashboardIssue:
    code: str
    severity: DashboardSeverity
    title: str
    detail: str
    suggested_action: str | None = None


@dataclass(frozen=True)
class StatusSnapshot:
    wordlist_count: int
    diffs: tuple[DictionaryDiff, ...]
    skipped_unreadable: tuple[str, ...]
    skipped_corrupt: tuple[str, ...]
    wordlist_error: ExitCode | None = None
    destructive_risk: str | None = None
    empty_wordlist: bool = False
    honesty_warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class TargetStatusRow:
    name: str
    enabled: bool
    available: bool
    read_status: str
    path: str
    format: str
    word_count: int | None
    detail: str | None = None
    skipped_reason: str | None = None


@dataclass(frozen=True)
class StatusDetailSnapshot:
    wordlist_path: str
    project_dir: str
    config_path: str | None
    wordlist_count: int
    targets: tuple[TargetStatusRow, ...]
    skipped_unreadable: tuple[str, ...]
    skipped_corrupt: tuple[str, ...]
    wordlist_error: ExitCode | None = None
    destructive_risk: str | None = None
    load_error: str | None = None
    warnings: tuple[str, ...] = ()

    @classmethod
    def unavailable(cls, load_error: str = "Status could not be loaded.") -> StatusDetailSnapshot:
        return cls(
            wordlist_path="",
            project_dir="",
            config_path=None,
            wordlist_count=0,
            targets=(),
            skipped_unreadable=(),
            skipped_corrupt=(),
            load_error=load_error,
        )


@dataclass(frozen=True)
class DashboardState:
    wordlist_path: str
    project_dir: str
    config_status: str
    config_valid: bool
    targets_detected: int
    targets_enabled: int
    targets_available: int
    targets_ready: int
    targets_needs_attention: int
    targets_disabled: int
    targets_unavailable: int
    pending_recovery: bool
    overall_severity: DashboardSeverity
    overall_label: str
    issues: tuple[DashboardIssue, ...]
    snapshot: StatusSnapshot
    last_operation_summary: str | None = None


@dataclass(frozen=True)
class TargetPreview:
    name: str
    additions: int
    removals: int
    status: str
    removal_words: frozenset[str] = frozenset()
    addition_words: frozenset[str] = frozenset()


@dataclass(frozen=True)
class PushPreview:
    """Immutable push preview tied to one PreparedPush instance."""

    prepared: PreparedPush | None
    targets: tuple[TargetPreview, ...]
    additions: int
    removals: int
    warnings: tuple[str, ...]
    created_at: str
    plan_identifier: str
    targets_to_update: int
    unchanged: int
    skipped: tuple[str, ...]
    corrupt: tuple[str, ...]
    blocked: tuple[str, ...]
    prepare_error: ExitCode | None = None
    wordlist_error: ExitCode | None = None

    @property
    def is_executable(self) -> bool:
        return (
            self.prepared is not None and self.prepare_error is None and self.wordlist_error is None
        )

    @classmethod
    def unavailable(
        cls,
        *,
        created_at: str = "",
        plan_identifier: str = "unavailable",
        wordlist_error: ExitCode | None = None,
        prepare_error: ExitCode | None = None,
        warnings: tuple[str, ...] = (),
    ) -> PushPreview:
        """Empty preview used when the wordlist cannot be read or prepare is blocked."""
        return cls(
            prepared=None,
            targets=(),
            additions=0,
            removals=0,
            warnings=warnings,
            created_at=created_at,
            plan_identifier=plan_identifier,
            targets_to_update=0,
            unchanged=0,
            skipped=(),
            corrupt=(),
            blocked=(),
            wordlist_error=wordlist_error,
            prepare_error=prepare_error,
        )


@dataclass(frozen=True)
class DoctorCheckView:
    group: str
    level: str
    title: str
    detail: str
    suggested_action: str | None = None


@dataclass(frozen=True)
class DoctorSnapshot:
    checks: tuple[DoctorCheckView, ...]
    has_errors: bool
    load_error: str | None = None

    @classmethod
    def unavailable(cls, load_error: str = "Doctor report could not be loaded.") -> DoctorSnapshot:
        return cls(checks=(), has_errors=True, load_error=load_error)


@dataclass(frozen=True)
class DoctorTargetView:
    name: str
    path: str
    format: str
    read_status: str


@dataclass(frozen=True)
class DoctorTargetsSnapshot:
    wordlist_path: str
    targets: tuple[DoctorTargetView, ...]


class OperationOutcome(StrEnum):
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    STOPPED_SAFELY = "stopped_safely"
    RECOVERY_REQUIRED = "recovery_required"
    FAILED = "failed"


class OperationStage(StrEnum):
    PREPARING = "preparing"
    EXECUTING = "executing"
    ROLLING_BACK = "rolling_back"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class PullSourcePreview:
    name: str
    status: str
    words_contributed: int = 0
    detail: str | None = None
    path: str | None = None
    content_sha256: str | None = None


@dataclass(frozen=True)
class PullPreview:
    """Immutable pull preview with the exact merged wordlist for execution."""

    wordlist_path: str
    additions: int
    before_count: int
    after_count: int
    sources_used: tuple[str, ...]
    sources_skipped: tuple[str, ...]
    source_rows: tuple[PullSourcePreview, ...]
    warnings: tuple[str, ...]
    created_at: str
    plan_identifier: str
    merged_words: tuple[str, ...]
    addition_words: frozenset[str] = frozenset()
    wordlist_fingerprint: str | None = None
    runtime_identity: RuntimeIdentity | None = None
    prepare_error: ExitCode | None = None
    wordlist_error: ExitCode | None = None

    @property
    def is_executable(self) -> bool:
        return self.prepare_error is None and self.wordlist_error is None

    @classmethod
    def unavailable(
        cls,
        *,
        wordlist_path: str,
        created_at: str = "",
        plan_identifier: str = "unavailable",
        wordlist_error: ExitCode | None = None,
        prepare_error: ExitCode | None = None,
        sources_skipped: tuple[str, ...] = (),
        source_rows: tuple[PullSourcePreview, ...] = (),
        warnings: tuple[str, ...] = (),
    ) -> PullPreview:
        """Empty preview used when the wordlist or source cannot be read."""
        return cls(
            wordlist_path=wordlist_path,
            additions=0,
            before_count=0,
            after_count=0,
            sources_used=(),
            sources_skipped=sources_skipped,
            source_rows=source_rows,
            warnings=warnings,
            created_at=created_at,
            plan_identifier=plan_identifier,
            merged_words=(),
            wordlist_error=wordlist_error,
            prepare_error=prepare_error,
        )


@dataclass(frozen=True)
class PullExecution:
    preview: PullPreview
    result: tuple[int, int] | ExitCode
    outcome: OperationOutcome
    message: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class TargetUpdateReport:
    name: str
    additions: int
    removals: int
    status: str
    detail: str | None = None


@dataclass(frozen=True)
class OperationReport:
    operation: str
    outcome: OperationOutcome
    title: str
    summary: str
    details: tuple[str, ...] = ()
    target_updates: tuple[TargetUpdateReport, ...] = ()
    warnings: tuple[str, ...] = ()
    conflict_target: str | None = None
    recovery_required: bool = False
    plan_identifier: str | None = None


@dataclass(frozen=True)
class PushExecution:
    """Outcome of push prepare/execute using one PreparedPush instance."""

    prepared: PreparedPush | None
    result: PushResult | ExitCode
    outcome: OperationOutcome = OperationOutcome.COMPLETED
    message: str = ""
    conflict_target: str | None = None
    warnings: tuple[str, ...] = ()
    target_updates: tuple[TargetUpdateReport, ...] = ()
    recovery_required: bool = False
    plan_identifier: str | None = None
    push_preview: PushPreview | None = None


class RecoveryStatus(StrEnum):
    ABSENT = "absent"
    RECOVERABLE = "recoverable"
    COMPLETED_CLEANUP_PENDING = "completed_cleanup_pending"
    CONFLICTED = "conflicted"
    CORRUPT_JOURNAL = "corrupt_journal"
    UNSUPPORTED_SCHEMA = "unsupported_schema"
    RECOVERY_IN_PROGRESS = "recovery_in_progress"


@dataclass(frozen=True)
class RecoveryItemPreview:
    name: str
    path: str
    current_state: str
    recovery_action: str
    status: str
    detail: str | None = None
    existed_before: bool = True
    write_started: bool = False
    write_completed: bool = False
    snapshot_valid: bool = True


@dataclass(frozen=True)
class RecoveryPreview:
    status: RecoveryStatus
    transaction_id: str
    command: str
    transaction_state: str
    started_at: str
    wordlist_path: str
    snapshot_directory: str | None
    items: tuple[RecoveryItemPreview, ...]
    recoverable_count: int
    conflict_count: int
    failure_count: int
    warnings: tuple[str, ...]
    can_recover: bool
    can_discard: bool
    snapshots_valid: bool
    preview_fingerprint: str
    journal_summary: dict[str, object] = field(default_factory=dict)
    can_cleanup: bool = False
    detail: str | None = None
    load_error: str | None = None

    @classmethod
    def unavailable(
        cls,
        *,
        wordlist_path: str = "",
        status: RecoveryStatus = RecoveryStatus.ABSENT,
        detail: str | None = None,
        load_error: str | None = None,
        can_discard: bool = False,
        snapshots_valid: bool = False,
        preview_fingerprint: str = "absent",
    ) -> RecoveryPreview:
        """Empty preview when no journal exists or the preview cannot be loaded.

        Snapshots are unknown unless a caller proves they exist.
        """
        return cls(
            status=status,
            transaction_id="",
            command="",
            transaction_state="",
            started_at="",
            wordlist_path=wordlist_path,
            snapshot_directory=None,
            items=(),
            recoverable_count=0,
            conflict_count=0,
            failure_count=0,
            warnings=(),
            can_recover=False,
            can_discard=can_discard,
            snapshots_valid=snapshots_valid,
            preview_fingerprint=preview_fingerprint,
            detail=detail,
            load_error=load_error,
        )


class RecoveryOutcome(StrEnum):
    RECOVERED = "recovered"
    RECOVERED_WITH_WARNINGS = "recovered_with_warnings"
    CONFLICTED = "conflicted"
    RECOVERY_INCOMPLETE = "recovery_incomplete"
    CLEANUP_COMPLETED = "cleanup_completed"
    DISCARDED = "discarded"
    FAILED = "failed"


@dataclass(frozen=True)
class RecoveryExecution:
    preview: RecoveryPreview
    result: object
    outcome: RecoveryOutcome
    message: str
    warnings: tuple[str, ...] = ()
    restored: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
