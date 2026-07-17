"""Commands pull / push / status / lint / init."""

from __future__ import annotations

import sys
from pathlib import Path

from .app_process_check import (
    confirm_chrome_before_push,
    confirm_edge_before_push,
    confirm_firefox_before_push,
    confirm_obsidian_before_push,
)
from .bundled_files import init_project_directory
from .cli_options import CliOptions
from .command_helpers import (
    confirm_push_removals,
    emit_command_exit,
    finish_push,
    guard_exit_code,
    mutating_command_scope,
    print_status_diff,
    push_skip_running_app_dicts,
    quiet_json_output,
    sync_run_for,
    wordlist_file_for,
)
from .config import push_strict_enabled
from .dictionary_hints import warn_missing_optional_apps
from .exit_codes import ExitCode
from .json_output import base_payload, dictionary_diff_payload, emit_json
from .lint import run_lint
from .log import log
from .removal_review import review_removals_interactive
from .runtime import installed_package_version
from .sync_run import PushResult, SyncRun


def _effective_push_strict(opts: CliOptions) -> bool:
    return opts.strict or push_strict_enabled()


def _running_apps_check_for_push(opts: CliOptions) -> bool | None:
    interactive = sys.stdin.isatty() and not opts.yes and not opts.json_output
    for confirm in (
        confirm_chrome_before_push,
        confirm_edge_before_push,
        confirm_firefox_before_push,
        confirm_obsidian_before_push,
    ):
        choice = confirm(interactive=interactive)
        if choice is None or not choice:
            return choice
    return True


def _before_push_checks(run: SyncRun, opts: CliOptions) -> bool | None:
    choice = _running_apps_check_for_push(opts)
    if choice is None or not choice:
        return choice
    if opts.review_removals:
        choice = review_removals_interactive(run, interactive=not opts.json_output)
        if choice is None or not choice:
            return choice
    return confirm_push_removals(run, opts)


def cmd_status(opts: CliOptions) -> int:
    with quiet_json_output(opts):
        verbose = opts.verbose
        log.section("status" + (" (verbose)" if verbose else ""))
        run = sync_run_for(opts)
        wordlist_err = run.check_wordlist()
        if wordlist_err is not None:
            return emit_command_exit(opts, "status", wordlist_err)
        words = run.load_wordlist()
        if not words:
            log.warn("wordlist is empty — push will abort; dictionaries won't change.")
        else:
            risk = run.destructive_push_risk()
            if risk:
                log.warn(risk)
        diffs = run.status_diffs(verbose=verbose)
        if opts.json_output:
            emit_json(
                {
                    **base_payload("status", exit=int(ExitCode.OK)),
                    "version": installed_package_version(),
                    "wordlist_count": len(words),
                    "skipped_unreadable": list(run.skipped_unreadable_dictionary_names()),
                    "skipped_corrupt": list(run.skipped_corrupt_dictionary_names()),
                    "dictionaries": [dictionary_diff_payload(d) for d in diffs],
                }
            )
            return int(ExitCode.OK)
        for diff in diffs:
            print_status_diff(diff, verbose=verbose)
        return int(ExitCode.OK)


def cmd_pull(opts: CliOptions) -> int:
    with quiet_json_output(opts):
        with mutating_command_scope(opts, "pull") as scope:
            if isinstance(scope, int):
                return scope
            return _cmd_pull_locked(opts)


def _cmd_pull_locked(opts: CliOptions) -> int:
    run = sync_run_for(opts)
    if opts.add_from:
        log.section(f"pull: merge words from {opts.add_from} -> wordlist")
        result = run.pull_add_from(opts.add_from)
    else:
        log.section("pull: merge new words from dictionaries -> wordlist (union)")
        result = run.pull_into_wordlist()
    if isinstance(result, ExitCode):
        return emit_command_exit(opts, "pull", result)
    before, after = result
    source = opts.add_from
    if opts.json_output:
        emit_json(
            {
                **base_payload("pull", exit=int(ExitCode.OK)),
                "before": before,
                "after": after,
                "added": after - before,
                "source": source,
            }
        )
        return int(ExitCode.OK)
    log.done(f"wordlist: {before} -> {after} (+{after - before})")
    return int(ExitCode.OK)


def cmd_push(opts: CliOptions) -> int:
    with quiet_json_output(opts):
        with mutating_command_scope(
            opts,
            "push",
            strict_push=_effective_push_strict(opts),
        ) as scope:
            if isinstance(scope, int):
                return scope
            return _cmd_push_locked(opts)


def _cmd_push_locked(opts: CliOptions) -> int:
    dry_run = opts.dry_run
    mode = " (dry-run)" if dry_run else ""
    log.section(f"push{mode}: wordlist OVERWRITES all dictionaries")
    warn_missing_optional_apps()
    run = sync_run_for(opts, strict_push=_effective_push_strict(opts))
    skip_names = push_skip_running_app_dicts(run, opts)
    prepared = run.prepare_push_operation(skip_names=skip_names)
    if isinstance(prepared, ExitCode):
        return finish_push(prepared, opts, dry_run=dry_run, command="push")
    if not dry_run:
        exit_code = guard_exit_code(
            _running_apps_check_for_push(opts),
            cancelled=ExitCode.CANCELLED,
            quiet=opts.json_output,
        )
        if exit_code is not None:
            code = ExitCode(exit_code)
            action = "interrupted" if code is ExitCode.SYNC_INTERRUPTED else "cancelled"
            return emit_command_exit(
                opts,
                "push",
                code,
                dry_run=dry_run,
                action=action,
                reason="running_apps_check",
            )
        if opts.review_removals:
            exit_code = guard_exit_code(
                review_removals_interactive(run),
                cancelled=ExitCode.CANCELLED,
                quiet=opts.json_output,
            )
            if exit_code is not None:
                code = ExitCode(exit_code)
                action = "interrupted" if code is ExitCode.SYNC_INTERRUPTED else "cancelled"
                return emit_command_exit(
                    opts,
                    "push",
                    code,
                    dry_run=dry_run,
                    action=action,
                    reason="review_removals",
                )
        exit_code = guard_exit_code(
            confirm_push_removals(run, opts, peak_removals=prepared.max_removals()),
            cancelled=ExitCode.CANCELLED,
            quiet=opts.json_output,
        )
        if exit_code is not None:
            code = ExitCode(exit_code)
            action = "interrupted" if code is ExitCode.SYNC_INTERRUPTED else "cancelled"
            return emit_command_exit(
                opts,
                "push",
                code,
                dry_run=dry_run,
                action=action,
                reason="confirm_push_removals",
            )
    if dry_run:
        result = run._run_push_transaction(dry_run=True, prepared=prepared)
    else:
        result = run.push_from_wordlist(prepared=prepared)
    if dry_run and isinstance(result, PushResult) and not opts.json_output:
        for diff in run.status_diffs(verbose=opts.verbose):
            print_status_diff(diff, verbose=opts.verbose)
    return finish_push(result, opts, dry_run=dry_run, command="push")


def cmd_init(opts: CliOptions) -> int:
    with quiet_json_output(opts):
        log.section("init: create wordlist and config from bundled examples")
        if opts.wordlist:
            target = wordlist_file_for(opts).parent
        else:
            target = Path.cwd()
        created = init_project_directory(target)
        if opts.json_output:
            emit_json({**base_payload("init", exit=int(ExitCode.OK)), "created": created})
            return int(ExitCode.OK)
        if created:
            for name in created:
                log.done(f"created {name}")
            log.info("next: edit wordlist.txt, then spell-sync pull or spell-sync push")
        else:
            log.info(
                "nothing to create — wordlist.txt, spell-sync.toml, "
                "and lint-whitelist.txt already exist."
            )
        return int(ExitCode.OK)


def cmd_lint(opts: CliOptions) -> int:
    with quiet_json_output(opts):
        if opts.fix:
            with mutating_command_scope(opts, "lint") as scope:
                if isinstance(scope, int):
                    return scope
                return _cmd_lint_locked(opts)
        return _cmd_lint_locked(opts)


def _cmd_lint_locked(opts: CliOptions) -> int:
    code = run_lint(
        wordlist_file_for(opts),
        fix=opts.fix,
        strict=opts.strict,
    )
    if opts.json_output:
        emit_json(base_payload("lint", exit=int(code)))
    return int(code)
