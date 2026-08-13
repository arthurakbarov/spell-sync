"""Environment diagnostics: paths, permissions, drift."""

import sys

from .application import SpellSyncService
from .cli_options import CliOptions
from .cli_request_adapter import doctor_request
from .command_helpers import quiet_json_output
from .exit_codes import ExitCode
from .health import (
    CliStatus,
    DoctorAction,
    DoctorCheck,
    DoctorReport,
    build_doctor_report,
    doctor_payload,
    format_action_line,
)
from .health.serialize import doctor_command_payload, doctor_report_exit_code
from .json_output import base_payload, emit_json
from .log import log
from .operation_presenter import OperationSpec, operation_session

__all__ = [
    "CliStatus",
    "DoctorAction",
    "DoctorCheck",
    "DoctorReport",
    "build_doctor_report",
    "cmd_doctor",
    "doctor_payload",
]

_SERVICE = SpellSyncService(enable_file_logging=False)


def cmd_doctor(opts: CliOptions) -> int:
    with quiet_json_output(opts):
        request = doctor_request(opts)
        if request.list_targets:
            with operation_session(
                OperationSpec(
                    key="doctor",
                    title="doctor: discovered dictionary paths",
                    descriptions=(
                        "List application custom dictionary paths found on this machine.",
                    ),
                    activity="List dictionary paths",
                ),
                enabled=not opts.json_output,
            ) as session:
                snapshot = _SERVICE.load_doctor_targets(request)
                targets = [
                    {
                        "name": item.name,
                        "path": item.path,
                        "format": item.format,
                        "read_status": item.read_status,
                    }
                    for item in snapshot.targets
                ]
                if opts.json_output:
                    emit_json(
                        {
                            **base_payload("doctor", exit=int(ExitCode.OK)),
                            "targets": True,
                            "wordlist": snapshot.wordlist_path,
                            "count": len(targets),
                            "targets_list": targets,
                        }
                    )
                    return int(ExitCode.OK)

                if not targets:
                    if session is not None:
                        session.succeed("no dictionary targets discovered for this platform")
                    else:
                        log.detail("no application dictionaries discovered for this platform")
                    return int(ExitCode.OK)
                for item in targets:
                    log.info(
                        f"{item['name']}: {item['path']} ({item['format']}, {item['read_status']})"
                    )
                if session is not None:
                    session.succeed(f"targets: {len(targets)} dictionary path(s)")
                else:
                    log.done(f"targets: {len(targets)} dictionary path(s)")
                return int(ExitCode.OK)

        if request.health_check:
            report = _SERVICE.load_doctor_report(request)
            if opts.json_output:
                exit_code = doctor_report_exit_code(report, health_check=True)
                payload = doctor_command_payload(report, health_check=True)
                payload.update(base_payload("doctor", exit=int(exit_code)))
                emit_json(payload)
                return int(exit_code)
            if report.has_errors:
                for check in report.checks:
                    if check.level == "error":
                        log.write(check.message, file=sys.stderr)
                return int(ExitCode.PUSH_ABORT)
            if report.required_actions:
                for action in report.required_actions:
                    log.write(format_action_line(action), file=sys.stderr)
                return int(ExitCode.LINT_FAILED)
            for action in report.optional_actions:
                log.write(format_action_line(action), file=sys.stderr)
            return int(ExitCode.OK)

        with operation_session(
            OperationSpec(
                key="doctor",
                title="doctor: environment and drift check",
                descriptions=(
                    "Check word list, dictionary access, and whether apps need an update.",
                ),
                activity="Health check",
            ),
            enabled=not opts.json_output,
        ) as session:
            if session is not None:
                session.note("Gathering environment and dictionary status.")
            report = _SERVICE.load_doctor_report(request)
            if opts.json_output:
                exit_code = doctor_report_exit_code(report, health_check=False)
                payload = doctor_command_payload(report, health_check=False)
                payload.update(base_payload("doctor", exit=int(exit_code)))
                emit_json(payload)
                return int(exit_code)

            log.info(f"spell-sync {report.package_version}")
            log.info(f"wordlist: {report.wordlist_path} ({report.wordlist_count} words)")
            log.info(
                f"dictionaries: {report.dictionaries_readable}/{report.dictionaries_total} "
                f"readable, "
                f"{report.dictionaries_writable}/{report.dictionaries_total} writable"
            )
            if report.wordlist_count:
                log.info(
                    f"drift: up to +{report.max_drift_add} / -{report.max_drift_remove} "
                    "words on push"
                )
            for check in report.checks:
                if check.level == "error":
                    log.error(check.message)
                elif check.level == "warn":
                    log.warn(check.message)
                else:
                    log.detail(check.message)

            if report.actions:
                log.info("next steps:")
                for action in report.actions:
                    if action.command:
                        log.detail(action.command)
                    elif action.shell:
                        log.detail(action.shell)
                    elif action.hint:
                        log.detail(action.hint)

            if report.has_errors:
                if session is not None:
                    session.fail("doctor found blocking issues")
                return int(ExitCode.PUSH_ABORT)
            if session is not None:
                session.succeed("doctor: no blocking issues")
            else:
                log.done("doctor: no blocking issues")
            return int(ExitCode.OK)
