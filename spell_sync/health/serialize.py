"""JSON payload fragments for doctor/health output."""

from __future__ import annotations

import shlex

from ..exit_codes import ExitCode
from .types import CliStatus, DoctorAction, DoctorCheck, DoctorReport, GitHooksStatus


def git_hooks_payload(status: GitHooksStatus | None) -> dict[str, bool] | None:
    if status is None:
        return None
    return {
        "pre_push": status.pre_push,
        "pre_commit": status.pre_commit,
        "pre_push_stale": status.pre_push_stale,
    }


def cli_status_payload(status: CliStatus) -> dict[str, object]:
    return {
        "on_path": status.on_path,
        "argv": list(status.argv),
        "executable": status.executable,
        "pip_script": status.pip_script,
        "path_export": status.path_export,
        "command_prefix": " ".join(shlex.quote(part) for part in status.argv),
    }


def doctor_action_payload(action: DoctorAction) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": action.id,
        "reason": action.reason,
        "optional": action.optional,
    }
    if action.command:
        payload["command"] = action.command
    if action.shell:
        payload["shell"] = action.shell
    if action.hint:
        payload["hint"] = action.hint
    return payload


def doctor_check_payload(check: DoctorCheck) -> dict[str, str]:
    return {"level": check.level, "message": check.message}


def doctor_payload(report: DoctorReport) -> dict[str, object]:
    return {
        "wordlist_path": report.wordlist_path,
        "wordlist_count": report.wordlist_count,
        "version": report.package_version,
        "skipped_unreadable": list(report.skipped_unreadable),
        "git_hooks": git_hooks_payload(report.git_hooks),
        "cli": cli_status_payload(report.cli),
        "dictionaries_total": report.dictionaries_total,
        "dictionaries_readable": report.dictionaries_readable,
        "dictionaries_writable": report.dictionaries_writable,
        "max_drift_add": report.max_drift_add,
        "max_drift_remove": report.max_drift_remove,
        "actions": [doctor_action_payload(action) for action in report.actions],
        "required_action_count": len(report.required_actions),
        "checks": [doctor_check_payload(check) for check in report.checks],
    }


def doctor_report_exit_code(report: DoctorReport, *, health_check: bool) -> ExitCode:
    if report.has_errors:
        return ExitCode.PUSH_ABORT
    if health_check and report.required_actions:
        return ExitCode.LINT_FAILED
    return ExitCode.OK


def doctor_command_payload(report: DoctorReport, *, health_check: bool) -> dict[str, object]:
    payload = doctor_payload(report)
    if health_check:
        payload["ok"] = not report.has_errors and not report.required_actions
        payload["action_count"] = len(report.actions)
    else:
        payload["ok"] = not report.has_errors
    return payload
