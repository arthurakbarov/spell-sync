"""Preview push without writing."""

from .application import SpellSyncService
from .cli_options import CliOptions
from .cli_request_adapter import push_request, status_request
from .command_helpers import (
    emit_command_exit,
    finish_push,
    print_status_diff,
    quiet_json_output,
)
from .exit_codes import ExitCode
from .json_output import base_payload, dictionary_diff_payload, emit_json, push_result_payload
from .log import log
from .operation_presenter import OperationSpec, operation_session
from .removal_review import list_removals_from_preview, print_removals
from .sync_run import PushResult

_SERVICE = SpellSyncService(enable_file_logging=False)


def cmd_plan(opts: CliOptions) -> int:
    with quiet_json_output(opts):
        request = push_request(opts)
        if opts.plan_removals:
            with operation_session(
                OperationSpec(
                    key="plan",
                    title="plan: words push would remove from dictionaries",
                    descriptions=(
                        "Show which words an update would remove from application dictionaries.",
                    ),
                    activity="Plan removals",
                ),
                enabled=not opts.json_output,
            ) as session:
                preview = _SERVICE.load_push_preview(request)
                if not preview.is_executable:
                    code = preview.wordlist_error or preview.prepare_error or ExitCode.PUSH_ABORT
                    if session is not None:
                        session.fail("plan could not build a removal preview.")
                    return emit_command_exit(opts, "plan", code)
                warnings = _plan_honesty_warnings(opts, preview)
                diffs = list_removals_from_preview(preview)
                if opts.json_output:
                    emit_json(
                        {
                            **base_payload("plan", exit=int(ExitCode.OK)),
                            "removals": True,
                            "warnings": warnings,
                            "dictionaries": [
                                {
                                    "name": diff.name,
                                    "to_remove": diff.to_remove,
                                    "remove_words": list(diff.remove_words),
                                }
                                for diff in diffs
                            ],
                        }
                    )
                    return int(ExitCode.OK)

                for warning in warnings:
                    log.warn(warning)
                if not diffs:
                    if session is not None:
                        session.succeed(
                            "no removals — push would only add or leave words unchanged"
                        )
                    else:
                        log.done("no removals — push would only add or leave words unchanged")
                    return int(ExitCode.OK)
                print_removals(diffs)
                if session is not None:
                    session.succeed(f"plan: {len(diffs)} dictionary target(s) with removals")
                return int(ExitCode.OK)

        with operation_session(
            OperationSpec(
                key="plan",
                title="plan: preview push (no writes)",
                descriptions=(
                    "Preview how Update my apps would change dictionaries without writing.",
                ),
                activity="Plan update",
            ),
            enabled=not opts.json_output,
        ) as session:
            if session is not None:
                session.note("Building push preview.")
            preview, diffs, result = _SERVICE.load_push_plan(request, verbose=opts.verbose)
            if not preview.is_executable:
                code = preview.wordlist_error or preview.prepare_error or ExitCode.PUSH_ABORT
                if session is not None:
                    session.fail("plan could not read the word list.")
                return emit_command_exit(opts, "plan", code)
            status = _SERVICE.load_status(status_request(opts))
            warnings = _plan_honesty_warnings(opts, preview)

            if opts.json_output:
                exit_code = ExitCode.OK
                payload: dict[str, object] = {
                    **base_payload("plan", exit=int(exit_code)),
                    "dry_run": True,
                    "wordlist_count": status.wordlist_count,
                    "warnings": warnings,
                    "dictionaries": [dictionary_diff_payload(diff) for diff in diffs],
                }
                if isinstance(result, PushResult):
                    payload.update(push_result_payload(result))
                    payload["partial"] = bool(result.skipped)
                else:
                    exit_code = ExitCode(result)
                    payload["exit"] = int(exit_code)
                emit_json(payload)
                return int(exit_code)

            for warning in warnings:
                log.warn(warning)
            for diff in diffs:
                print_status_diff(diff, verbose=opts.verbose)
            return finish_push(result, opts, dry_run=True, command="plan", session=session)


def _plan_honesty_warnings(opts: CliOptions, preview) -> list[str]:
    return list(preview.warnings)
