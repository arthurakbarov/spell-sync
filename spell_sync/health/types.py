"""Health report datatypes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CliStatus:
    on_path: bool
    argv: tuple[str, ...]
    executable: str | None
    pip_script: str | None
    path_export: str | None


@dataclass(frozen=True)
class GitHooksStatus:
    pre_push: bool
    pre_commit: bool
    pre_push_stale: bool


@dataclass(frozen=True)
class DoctorAction:
    id: str
    reason: str
    command: str | None = None
    shell: str | None = None
    hint: str | None = None
    optional: bool = False


@dataclass(frozen=True)
class DoctorCheck:
    level: str
    message: str


@dataclass(frozen=True)
class DoctorReport:
    wordlist_path: str
    wordlist_count: int
    package_version: str
    skipped_unreadable: tuple[str, ...]
    git_hooks: GitHooksStatus | None
    cli: CliStatus
    actions: tuple[DoctorAction, ...]
    checks: tuple[DoctorCheck, ...]
    dictionaries_total: int
    dictionaries_readable: int
    dictionaries_writable: int
    max_drift_add: int
    max_drift_remove: int

    @property
    def has_errors(self) -> bool:
        return any(check.level == "error" for check in self.checks)

    @property
    def required_actions(self) -> tuple[DoctorAction, ...]:
        return tuple(action for action in self.actions if not action.optional)

    @property
    def optional_actions(self) -> tuple[DoctorAction, ...]:
        return tuple(action for action in self.actions if action.optional)


def format_action_line(action: DoctorAction) -> str:
    if action.command:
        return f"{action.id}: {action.command} ({action.reason})"
    if action.shell:
        return f"{action.id}: {action.shell} ({action.reason})"
    if action.hint:
        return f"{action.id}: {action.hint} ({action.reason})"
    return f"{action.id}: {action.reason}"
