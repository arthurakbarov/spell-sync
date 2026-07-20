"""Immutable UI-neutral application requests."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..config import push_strict_enabled
from ..paths import resolve_wordlist_path


@dataclass(frozen=True, slots=True)
class ProjectRef:
    """Unresolved project wordlist selection from the caller."""

    wordlist: Path | None = None


def resolve_project_wordlist(project: ProjectRef) -> Path:
    """Resolve effective wordlist path using standard project rules."""
    if project.wordlist is None:
        return resolve_wordlist_path(None)
    return resolve_wordlist_path(str(project.wordlist))


class OperationSource(str, Enum):
    CLI = "cli"
    TUI = "tui"


@dataclass(frozen=True, slots=True)
class StatusRequest:
    project: ProjectRef
    include_word_diffs: bool = False


@dataclass(frozen=True, slots=True)
class DoctorRequest:
    project: ProjectRef


@dataclass(frozen=True, slots=True)
class PullRequest:
    project: ProjectRef
    add_from: Path | None = None


@dataclass(frozen=True, slots=True)
class PushRequest:
    project: ProjectRef
    strict_override: bool | None = None


@dataclass(frozen=True, slots=True)
class RecoveryRequest:
    project: ProjectRef


@dataclass(frozen=True, slots=True)
class SetupRequest:
    project: ProjectRef
    allow_new_project_wizard: bool = True


@dataclass(frozen=True, slots=True)
class TargetSettingsRequest:
    project: ProjectRef


@dataclass(frozen=True, slots=True)
class PrepareTargetSettingsUpdateRequest:
    project: ProjectRef
    selected_target_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class SupportReportRequest:
    project: ProjectRef


@dataclass(frozen=True, slots=True)
class ConfigCheckRequest:
    project: ProjectRef


@dataclass(frozen=True, slots=True)
class LintRequest:
    project: ProjectRef
    fix: bool = False
    strict: bool = False


def effective_push_strict(request: PushRequest) -> bool:
    if request.strict_override is not None:
        return request.strict_override
    return push_strict_enabled()
