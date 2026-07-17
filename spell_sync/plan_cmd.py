"""Preview push without writing."""

from __future__ import annotations

from .cli_options import CliOptions
from .command_helpers import (
    finish_push,
    print_status_diff,
    push_skip_running_app_dicts,
    quiet_json_output,
    sync_run_for,
)
from .config import push_strict_enabled
from .exit_codes import ExitCode
from .json_output import base_payload, dictionary_diff_payload, emit_json, push_result_payload
from .log import log
from .removal_review import list_removals, print_removals
from .sync_run import PushResult


def _effective_push_strict(opts: CliOptions) -> bool:
    return opts.strict or push_strict_enabled()


def _cmd_plan_removals(opts: CliOptions, run) -> int:
    wordlist_err = run.check_wordlist()
    if wordlist_err is not None:
        from .command_helpers import emit_command_exit

        return emit_command_exit(opts, "plan", wordlist_err)

    diffs = list_removals(run)
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


def cmd_plan(opts: CliOptions) -> int:
    with quiet_json_output(opts):
        run = sync_run_for(opts, strict_push=_effective_push_strict(opts))
        if opts.plan_removals:
            return _cmd_plan_removals(opts, run)

        log.section("plan: preview push (no writes)")
        wordlist_err = run.check_wordlist()
        if wordlist_err is not None:
            from .command_helpers import emit_command_exit

            return emit_command_exit(opts, "plan", wordlist_err)

        diffs = run.status_diffs(verbose=opts.verbose)
        skip_names = push_skip_running_app_dicts(run, opts)
        result = run.plan_push(skip_names=skip_names)

        if opts.json_output:
            exit_code = ExitCode.OK
            payload: dict[str, object] = {
                **base_payload("plan", exit=int(exit_code)),
                "dry_run": True,
                "wordlist_count": len(run.load_wordlist()),
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
