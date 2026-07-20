"""Immutable UI-neutral application request DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ProjectRef:
    """Unresolved project wordlist selection from the caller."""

    wordlist: Path | None = None


@dataclass(frozen=True, slots=True)
class StatusRequest:
    project: ProjectRef
    include_word_diffs: bool = False


@dataclass(frozen=True, slots=True)
class DoctorRequest:
    project: ProjectRef
    list_targets: bool = False
    health_check: bool = False


@dataclass(frozen=True, slots=True)
class PullRequest:
    project: ProjectRef
    add_from: Path | None = None
    json_output: bool = False


@dataclass(frozen=True, slots=True)
class PushRequest:
    project: ProjectRef
    strict_override: bool | None = None
    json_output: bool = False


@dataclass(frozen=True, slots=True)
class RecoveryRequest:
    project: ProjectRef
    json_output: bool = False


@dataclass(frozen=True, slots=True)
class SetupRequest:
    project: ProjectRef
    allow_project_creation: bool = True


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
