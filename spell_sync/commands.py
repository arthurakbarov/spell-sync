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
from .application import SpellSyncService
from .cli_options import CliOptions
from .command_helpers import (
    confirm_push_removals,
    emit_command_exit,
    finish_push,
    guard_exit_code,
    mutating_command_scope,
    print_status_diff,
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

_SERVICE = SpellSyncService()


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
        snapshot = _SERVICE.load_status(opts)
        if snapshot.wordlist_error is not None:
            return emit_command_exit(opts, "status", snapshot.wordlist_error)
        if snapshot.empty_wordlist:
            log.warn("wordlist is empty — push will abort; dictionaries won't change.")
        elif snapshot.destructive_risk:
            log.warn(snapshot.destructive_risk)
        if opts.json_output:
            emit_json(
                {
                    **base_payload("status", exit=int(ExitCode.OK)),
                    "version": installed_package_version(),
                    "wordlist_count": snapshot.wordlist_count,
                    "skipped_unreadable": list(snapshot.skipped_unreadable),
                    "skipped_corrupt": list(snapshot.skipped_corrupt),
                    "dictionaries": [dictionary_diff_payload(d) for d in snapshot.diffs],
                }
            )
            return int(ExitCode.OK)
        for diff in snapshot.diffs:
            print_status_diff(diff, verbose=verbose)
        return int(ExitCode.OK)


def cmd_pull(opts: CliOptions) -> int:
    with quiet_json_output(opts):
        with mutating_command_scope(opts, "pull") as scope:
            if isinstance(scope, int):
                return scope
            return _cmd_pull_locked(opts)


def _cmd_pull_locked(opts: CliOptions) -> int:
    preview = _SERVICE.prepare_pull(opts)
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
    _SERVICE.build_pull_report(_SERVICE.pull_execution_from_result(preview, (before, after)))
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
    prepared = _SERVICE.prepare_push(run, opts)
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
    result = _SERVICE.execute_push(run, prepared, dry_run=dry_run)
    if dry_run and isinstance(result, PushResult) and not opts.json_output:
        snapshot = _SERVICE.load_status(opts)
        for diff in snapshot.diffs:
            print_status_diff(diff, verbose=opts.verbose)
    if not dry_run and not isinstance(result, ExitCode):
        _SERVICE.build_push_report(_SERVICE.push_execution_from_result(prepared, result))
    return finish_push(result, opts, dry_run=dry_run, command="push")


def cmd_init(opts: CliOptions) -> int:
    from .application import SpellSyncService
    from .paths import resolve_wordlist_path
    from .project_setup.discovery import discover_setup_targets
    from .project_setup.draft import SetupDraft

    with quiet_json_output(opts):
        log.section("init: create wordlist and config from bundled examples")
        if opts.wordlist:
            wordlist = resolve_wordlist_path(opts.wordlist)
        else:
            wordlist = Path.cwd() / "wordlist.txt"
        discovery = discover_setup_targets()
        draft = SetupDraft(
            wordlist_path=wordlist,
            selected_targets=discovery.default_enabled,
            create_wordlist=not wordlist.is_file(),
        )
        service = SpellSyncService(enable_file_logging=False)
        prepared = service.prepare_project_setup(draft)
        if not prepared.can_execute:
            if opts.json_output:
                emit_json(
                    {
                        **base_payload("init", exit=int(ExitCode.OK)),
                        "created": [],
                        "outcome": "stopped_safely",
                    }
                )
                return int(ExitCode.OK)
            log.info(
                "nothing to create — wordlist.txt, spell-sync.toml, "
                "and lint-whitelist.txt already exist."
            )
            return int(ExitCode.OK)
        execution = service.execute_project_setup(
            prepared,
            confirmed_setup_id=prepared.setup_id,
        )
        service.build_setup_report(execution)
        if opts.json_output:
            emit_json(
                {
                    **base_payload("init", exit=int(ExitCode.OK)),
                    "created": list(execution.created_files),
                    "outcome": execution.outcome.value,
                }
            )
            return int(ExitCode.OK)
        if execution.outcome.value != "completed":
            log.error(execution.message)
            return int(ExitCode.PUSH_ABORT)
        for name in execution.created_files:
            log.done(f"created {name}")
        if not execution.created_files:
            log.info("nothing to create — project files already exist.")
        else:
            log.info("next: edit wordlist.txt, then spell-sync pull or spell-sync push")
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
