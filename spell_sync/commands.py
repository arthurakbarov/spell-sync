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
from .cli_request_adapter import pull_request, push_request, status_request
from .command_helpers import (
    confirm_push_removals_for_preview,
    emit_command_exit,
    finish_push,
    guard_exit_code,
    print_status_diff,
    quiet_json_output,
)
from .dictionary_hints import warn_missing_optional_apps
from .exit_codes import ExitCode
from .json_output import base_payload, dictionary_diff_payload, emit_json
from .lint import run_lint
from .log import log
from .removal_review import review_removals_for_preview
from .runtime import installed_package_version

_SERVICE = SpellSyncService()


def _running_apps_check_for_push(opts: CliOptions, preview) -> bool | None:
    interactive = sys.stdin.isatty() and not opts.yes and not opts.json_output
    prepared = preview.prepared
    settings = prepared.ctx.settings if prepared is not None else None
    if settings is None:
        from .runtime_settings import RuntimeSettings

        settings = RuntimeSettings.defaults()
    for confirm in (
        lambda: confirm_chrome_before_push(interactive=interactive, settings=settings),
        lambda: confirm_edge_before_push(interactive=interactive, settings=settings),
        lambda: confirm_firefox_before_push(interactive=interactive, settings=settings),
        lambda: confirm_obsidian_before_push(interactive=interactive, settings=settings),
    ):
        choice = confirm()
        if choice is None or not choice:
            return choice
    return True


def cmd_status(opts: CliOptions) -> int:
    with quiet_json_output(opts):
        verbose = opts.verbose
        log.section("status" + (" (verbose)" if verbose else ""))
        snapshot = _SERVICE.load_status(status_request(opts))
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
        return _cmd_pull_via_service(opts)


def _cmd_pull_via_service(opts: CliOptions) -> int:
    request = pull_request(opts)
    blocked = _SERVICE.mutating_config_exit_code(request, "pull")
    if blocked is not None:
        return int(blocked)
    preview = _SERVICE.prepare_pull(request)
    if not preview.is_executable:
        code = preview.wordlist_error or preview.prepare_error or ExitCode.PUSH_ABORT
        return emit_command_exit(opts, "pull", code)
    if opts.add_from:
        log.section(f"pull: merge words from {opts.add_from} -> wordlist")
    else:
        log.section("pull: merge new words from dictionaries -> wordlist (union)")
    execution = _SERVICE.execute_pull(
        request,
        preview,
        confirmed_plan_id=preview.plan_identifier,
    )
    if isinstance(execution.result, ExitCode):
        return emit_command_exit(opts, "pull", execution.result)
    before, after = execution.result
    _SERVICE.build_pull_report(execution)
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
        return _cmd_push_via_service(opts)


def _cmd_push_via_service(opts: CliOptions) -> int:
    dry_run = opts.dry_run
    mode = " (dry-run)" if dry_run else ""
    log.section(f"push{mode}: wordlist OVERWRITES all dictionaries")
    warn_missing_optional_apps()
    request = push_request(opts)
    blocked = _SERVICE.mutating_config_exit_code(request, "push")
    if blocked is not None:
        return int(blocked)
    preview = _SERVICE.load_push_preview(request)
    if not preview.is_executable:
        code = preview.wordlist_error or preview.prepare_error or ExitCode.PUSH_ABORT
        return finish_push(code, opts, dry_run=dry_run, command="push")
    if not dry_run:
        exit_code = guard_exit_code(
            _running_apps_check_for_push(opts, preview),
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
                review_removals_for_preview(
                    preview,
                    interactive=not opts.json_output,
                ),
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
            confirm_push_removals_for_preview(preview, opts),
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
        execution = _SERVICE.execute_push_dry_run(request, preview)
    else:
        execution = _SERVICE.execute_push_preview(
            request,
            preview,
            confirmed_plan_id=preview.plan_identifier,
        )
    result = execution.result
    if dry_run and not isinstance(result, ExitCode) and not opts.json_output:
        snapshot = _SERVICE.load_status(status_request(opts))
        for diff in snapshot.diffs:
            print_status_diff(diff, verbose=opts.verbose)
    if not dry_run:
        _SERVICE.build_push_report(execution)
    return finish_push(
        result,
        opts,
        dry_run=dry_run,
        command="push",
        recovery_required=execution.recovery_required,
        outcome=execution.outcome.value,
    )


def cmd_init(opts: CliOptions) -> int:
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
        ok = execution.outcome.value == "completed"
        exit_code = int(ExitCode.OK if ok else ExitCode.PUSH_ABORT)
        if opts.json_output:
            emit_json(
                {
                    **base_payload("init", exit=exit_code),
                    "created": list(execution.created_files),
                    "outcome": execution.outcome.value,
                }
            )
            return exit_code
        if not ok:
            log.error(execution.message)
            return exit_code
        for name in execution.created_files:
            log.done(f"created {name}")
        if not execution.created_files:
            log.info("nothing to create — project files already exist.")
        else:
            log.info("next: edit wordlist.txt, then spell-sync pull or spell-sync push")
            log.info(
                "optional: keep the folder local, in a synced cloud directory, "
                "or a private Git remote — see docs/PERSONAL_WORKSPACE.md"
            )
        return exit_code


def cmd_lint(opts: CliOptions) -> int:
    from .command_helpers import mutating_command_scope, wordlist_file_for

    with quiet_json_output(opts):
        if opts.fix:
            with mutating_command_scope(opts, "lint") as scope:
                if isinstance(scope, int):
                    return scope
                return _cmd_lint_locked(opts, wordlist_file_for(opts))
        return _cmd_lint_locked(opts, wordlist_file_for(opts))


def _cmd_lint_locked(opts: CliOptions, wordlist) -> int:
    code = run_lint(
        wordlist,
        fix=opts.fix,
        strict=opts.strict,
    )
    if opts.json_output:
        emit_json(base_payload("lint", exit=int(code)))
    return int(code)
