"""Map CLI parser DTOs to immutable application requests."""

from __future__ import annotations

from pathlib import Path

from .application.requests import (
    ConfigCheckRequest,
    DoctorRequest,
    LintRequest,
    ProjectRef,
    PullRequest,
    PushRequest,
    RecoveryRequest,
    SetupRequest,
    StatusRequest,
    SupportReportRequest,
    TargetSettingsRequest,
    effective_push_strict,
)
from .cli_options import CliOptions

__all__ = [
    "config_check_request",
    "doctor_request",
    "effective_push_strict",
    "lint_request",
    "project_ref",
    "pull_request",
    "push_request",
    "recovery_request",
    "setup_request",
    "status_request",
    "support_report_request",
    "target_settings_request",
]


def project_ref(options: CliOptions) -> ProjectRef:
    if options.wordlist is None or not options.wordlist.strip():
        return ProjectRef(wordlist=None)
    return ProjectRef(wordlist=Path(options.wordlist))


def status_request(options: CliOptions) -> StatusRequest:
    return StatusRequest(
        project=project_ref(options),
        include_word_diffs=options.verbose,
    )


def doctor_request(options: CliOptions) -> DoctorRequest:
    return DoctorRequest(project=project_ref(options))


def pull_request(options: CliOptions) -> PullRequest:
    add_from = None
    if options.add_from:
        add_from = Path(options.add_from)
    return PullRequest(project=project_ref(options), add_from=add_from)


def push_request(options: CliOptions) -> PushRequest:
    strict_override = True if options.strict else None
    return PushRequest(project=project_ref(options), strict_override=strict_override)


def recovery_request(options: CliOptions) -> RecoveryRequest:
    return RecoveryRequest(project=project_ref(options))


def setup_request(options: CliOptions) -> SetupRequest:
    explicit = options.wordlist is not None and bool(options.wordlist.strip())
    return SetupRequest(
        project=project_ref(options),
        allow_new_project_wizard=not explicit,
    )


def target_settings_request(options: CliOptions) -> TargetSettingsRequest:
    return TargetSettingsRequest(project=project_ref(options))


def support_report_request(options: CliOptions) -> SupportReportRequest:
    return SupportReportRequest(project=project_ref(options))


def config_check_request(options: CliOptions) -> ConfigCheckRequest:
    return ConfigCheckRequest(project=project_ref(options))


def lint_request(options: CliOptions) -> LintRequest:
    return LintRequest(
        project=project_ref(options),
        fix=options.fix,
        strict=options.strict,
    )
