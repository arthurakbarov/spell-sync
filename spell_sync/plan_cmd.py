"""Preview push without writing."""

from __future__ import annotations

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
from .removal_review import list_removals_from_preview, print_removals
from .sync_run import PushResult

_SERVICE = SpellSyncService(enable_file_logging=False)


def cmd_plan(opts: CliOptions) -> int:
    with quiet_json_output(opts):
        request = push_request(opts)
        if opts.plan_removals:
            preview = _SERVICE.load_push_preview(request)
            if preview.wordlist_error is not None:
                return emit_command_exit(opts, "plan", preview.wordlist_error)
            diffs = list_removals_from_preview(preview)
            if opts.json_output:
                emit_json(
                    {
                        **base_payload("plan", exit=int(ExitCode.OK)),
                        "removals": True,
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

            log.section("plan: words push would remove from dictionaries")
            if not diffs:
                log.done("no removals — push would only add or leave words unchanged")
                return int(ExitCode.OK)
            print_removals(diffs)
            return int(ExitCode.OK)

        log.section("plan: preview push (no writes)")
        preview, diffs, result = _SERVICE.load_push_plan(request, verbose=opts.verbose)
        if preview.wordlist_error is not None:
            return emit_command_exit(opts, "plan", preview.wordlist_error)
        status = _SERVICE.load_status(status_request(opts))

        if opts.json_output:
            exit_code = ExitCode.OK
            payload: dict[str, object] = {
                **base_payload("plan", exit=int(exit_code)),
                "dry_run": True,
                "wordlist_count": status.wordlist_count,
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

        for diff in diffs:
            print_status_diff(diff, verbose=opts.verbose)
        return finish_push(result, opts, dry_run=True, command="plan")
