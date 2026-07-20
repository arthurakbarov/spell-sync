"""support-report: export a redacted diagnostic report."""

from __future__ import annotations

from pathlib import Path

from .application.support_report import (
    build_support_report,
    default_support_report_path,
    export_support_report,
    format_support_report_text,
    support_report_to_dict,
)
from .cli_options import CliOptions
from .cli_request_adapter import support_report_request
from .command_helpers import emit_command_exit
from .exit_codes import ExitCode


def cmd_support_report(opts: CliOptions) -> int:
    from .application.service import SpellSyncService

    service = SpellSyncService()
    report = build_support_report(service, support_report_request(opts))
    fmt = getattr(opts, "support_report_format", "text") or "text"
    output = getattr(opts, "support_report_output", None)
    if opts.json_output and not output:
        payload = {**support_report_to_dict(report), "format": fmt}
        return emit_command_exit(opts, "support-report", ExitCode.OK, **payload)
    path = Path(output) if output else default_support_report_path(fmt=fmt)
    try:
        written = export_support_report(report, output_path=path, fmt=fmt)
    except FileExistsError as exc:
        return emit_command_exit(opts, "support-report", ExitCode.PUSH_ABORT, message=str(exc))
    if opts.json_output:
        payload = support_report_to_dict(report)
        payload["output_path"] = str(written)
        return emit_command_exit(opts, "support-report", ExitCode.OK, **payload)
    if fmt == "text" and not output:
        print(format_support_report_text(report))
        print(f"\nReport saved: {written}")
    else:
        print(written)
    return int(ExitCode.OK)
