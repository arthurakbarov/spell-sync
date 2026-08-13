"""support-report: export a redacted diagnostic report."""

from pathlib import Path

from .application.support_report import (
    default_support_report_path,
    export_support_report,
    format_support_report_text,
    support_report_to_dict,
)
from .cli_options import CliOptions
from .cli_request_adapter import support_report_request
from .command_helpers import emit_command_exit
from .exit_codes import ExitCode
from .log import log
from .operation_presenter import OperationSpec, operation_session


def cmd_support_report(opts: CliOptions) -> int:
    from .application.service import SpellSyncService

    with operation_session(
        OperationSpec(
            key="support-report",
            title="support-report: export redacted diagnostics",
            descriptions=("Build a privacy-safe diagnostic report for troubleshooting.",),
            activity="Support report",
        ),
        enabled=not opts.json_output,
    ) as session:
        service = SpellSyncService()
        if session is not None:
            session.note("Collecting redacted diagnostics.")
        report = service.build_support_report(support_report_request(opts))
        fmt = getattr(opts, "support_report_format", "text") or "text"
        output = getattr(opts, "support_report_output", None)
        if opts.json_output and not output:
            payload = {**support_report_to_dict(report), "format": fmt}
            return emit_command_exit(opts, "support-report", ExitCode.OK, **payload)
        path = Path(output) if output else default_support_report_path(fmt=fmt)
        try:
            written = export_support_report(report, output_path=path, fmt=fmt)
        except FileExistsError as exc:
            if session is not None:
                session.fail(str(exc))
            return emit_command_exit(opts, "support-report", ExitCode.PUSH_ABORT, message=str(exc))
        if opts.json_output:
            payload = support_report_to_dict(report)
            payload["output_path"] = str(written)
            return emit_command_exit(opts, "support-report", ExitCode.OK, **payload)
        if fmt == "text" and not output:
            log.write(format_support_report_text(report))
            log.write(f"\nReport saved: {written}")
        else:
            log.write(str(written))
        if session is not None:
            session.succeed(f"support report written: {written}")
        return int(ExitCode.OK)
