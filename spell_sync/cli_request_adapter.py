"""Map CLI parser DTOs to immutable application requests."""

from __future__ import annotations

from pathlib import Path

from .application.requests import (
    DoctorRequest,
    ProjectRef,
    PullRequest,
    PushRequest,
    RecoveryRequest,
    SetupRequest,
    StatusRequest,
    SupportReportRequest,
    TargetSettingsRequest,
)
from .cli_options import CliOptions

__all__ = [
    "doctor_request",
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
    return DoctorRequest(
        project=project_ref(options),
        list_targets=options.show_targets,
        health_check=options.health_check,
    )


def pull_request(options: CliOptions) -> PullRequest:
    add_from = None
    if options.add_from:
        add_from = Path(options.add_from)
    return PullRequest(
        project=project_ref(options),
        add_from=add_from,
        json_output=options.json_output,
    )


def push_request(options: CliOptions) -> PushRequest:
    strict_override = True if options.strict else None
    return PushRequest(
        project=project_ref(options),
        strict_override=strict_override,
        json_output=options.json_output,
    )


def recovery_request(options: CliOptions) -> RecoveryRequest:
    return RecoveryRequest(project=project_ref(options), json_output=options.json_output)


def setup_request(options: CliOptions) -> SetupRequest:
    explicit = options.wordlist is not None and bool(options.wordlist.strip())
    return SetupRequest(
        project=project_ref(options),
        allow_project_creation=not explicit,
    )


def target_settings_request(options: CliOptions) -> TargetSettingsRequest:
    return TargetSettingsRequest(project=project_ref(options))


def support_report_request(options: CliOptions) -> SupportReportRequest:
    return SupportReportRequest(project=project_ref(options))
