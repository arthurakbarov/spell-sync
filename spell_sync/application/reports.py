"""Structured application results shared by CLI and TUI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..exit_codes import ExitCode
from ..push_prepared import PreparedPush
from ..sync_models import DictionaryDiff, PushResult


class DashboardSeverity(str, Enum):
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
    config_paths: tuple[str, ...]
    wordlist_count: int
    targets: tuple[TargetStatusRow, ...]
    skipped_unreadable: tuple[str, ...]
    skipped_corrupt: tuple[str, ...]
    wordlist_error: ExitCode | None = None
    destructive_risk: str | None = None
    load_error: str | None = None


@dataclass(frozen=True)
class DashboardState:
    wordlist_path: str
    project_dir: str
    config_status: str
    config_valid: bool
    targets_detected: int
    targets_enabled: int
    targets_available: int
    pending_recovery: bool
    overall_severity: DashboardSeverity
    overall_label: str
    issues: tuple[DashboardIssue, ...]
    snapshot: StatusSnapshot


@dataclass(frozen=True)
class TargetPreview:
    name: str
    additions: int
    removals: int
    status: str
    removal_words: frozenset[str] = frozenset()


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


@dataclass(frozen=True)
class PushPreviewSnapshot:
    """Deprecated alias kept for transitional imports."""

    diffs: tuple[DictionaryDiff, ...]
    plan_result: PushResult | ExitCode | None = None
    wordlist_error: ExitCode | None = None


@dataclass(frozen=True)
class PushExecution:
    """Outcome of push prepare/execute using one PreparedPush instance."""

    prepared: PreparedPush
    result: PushResult | ExitCode
