"""Health diagnostics: doctor report building and inspection."""

from .actions import build_doctor_actions
from .inspect import git_hooks_checks, inspect_cli, inspect_git_hooks
from .report import build_doctor_report
from .serialize import doctor_payload
from .types import (
    CliStatus,
    DoctorAction,
    DoctorCheck,
    DoctorReport,
    GitHooksStatus,
    format_action_line,
)

__all__ = [
    "CliStatus",
    "DoctorAction",
    "DoctorCheck",
    "DoctorReport",
    "GitHooksStatus",
    "build_doctor_actions",
    "build_doctor_report",
    "doctor_payload",
    "format_action_line",
    "git_hooks_checks",
    "inspect_cli",
    "inspect_git_hooks",
]
