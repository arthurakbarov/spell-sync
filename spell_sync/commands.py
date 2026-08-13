"""Commands pull / push / status / lint / init."""

import sys
from pathlib import Path

from .app_process_check import (
    confirm_chrome_before_push,
    confirm_edge_before_push,
    confirm_firefox_before_push,
    confirm_obsidian_before_push,
)
from .application import SpellSyncService
from .application.product_concepts import COLLECT_WORDS_HELP, UPDATE_APPS_HELP
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
from .operation_presenter import OperationSpec, operation_session
from .removal_review import review_removals_for_preview
from .runtime import installed_package_version
from .runtime_settings import RuntimeSettings
from .settings import load_project_settings_with_issues

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
        title = "status" + (" (verbose)" if verbose else "")
        with operation_session(
            OperationSpec(
                key="status",
                title=title,
                descriptions=(
                    "Compare your personal word list with enabled application custom dictionaries.",
                ),
                activity="Check my apps",
            ),
            enabled=not opts.json_output,
        ) as session:
            snapshot = _SERVICE.load_status(status_request(opts))
            if snapshot.wordlist_error is not None:
                if session is not None:
                    session.fail("status could not read the word list.")
                return emit_command_exit(opts, "status", snapshot.wordlist_error)
            warnings: list[str] = []
            logged: set[str] = set()

            def _note(message: str, *, emit: bool = True) -> None:
                warnings.append(message)
                if emit and message not in logged:
                    log.warn(message)
                    logged.add(message)

            if snapshot.empty_wordlist:
                _note("wordlist is empty — push will abort; dictionaries won't change.")
            elif snapshot.destructive_risk:
                _note(snapshot.destructive_risk)
            from .application.project_resolution import resolve_project_wordlist
            from .cli_request_adapter import project_ref
            from .config import enable_sublime
            from .settings import load_project_settings_with_issues
            from .sublime_preferences import user_added_words_override_message
            from .workspace_git import inspect_workspace_git, workspace_git_dirty_message

            wl = resolve_project_wordlist(project_ref(opts))
            config, _ = load_project_settings_with_issues(wordlist=wl)
            settings = RuntimeSettings.from_config_dict(config)
            if enable_sublime(settings=settings):
                override = user_added_words_override_message()
                if override is not None:
                    _note(override)
            git_status = inspect_workspace_git(wl.parent)
            if git_status is not None and git_status.is_dirty:
                _note(workspace_git_dirty_message(git_status))
            if snapshot.skipped_unreadable:
                _note(f"Skipped unreadable: {', '.join(snapshot.skipped_unreadable)}")
            if snapshot.skipped_corrupt:
                _note(f"Skipped corrupt: {', '.join(snapshot.skipped_corrupt)}")
            if opts.json_output:
                emit_json(
                    {
                        **base_payload("status", exit=int(ExitCode.OK)),
                        "version": installed_package_version(),
                        "wordlist_count": snapshot.wordlist_count,
                        "skipped_unreadable": list(snapshot.skipped_unreadable),
                        "skipped_corrupt": list(snapshot.skipped_corrupt),
                        "dictionaries": [dictionary_diff_payload(d) for d in snapshot.diffs],
                        "warnings": warnings,
                    }
                )
                return int(ExitCode.OK)
            for diff in snapshot.diffs:
                print_status_diff(diff, verbose=verbose)
            if session is not None:
                session.succeed(f"status: {len(snapshot.diffs)} dictionary target(s) compared")
            return int(ExitCode.OK)


def cmd_pull(opts: CliOptions) -> int:
    with quiet_json_output(opts):
        return _cmd_pull_via_service(opts)


def _cmd_pull_via_service(opts: CliOptions) -> int:
    if opts.add_from:
        title = f"pull: merge words from {opts.add_from} -> wordlist"
    else:
        title = "pull: merge new words from dictionaries -> wordlist (union)"
    with operation_session(
        OperationSpec(
            key="pull",
            title=title,
            descriptions=(COLLECT_WORDS_HELP,),
            activity="Collect my words",
        ),
        enabled=not opts.json_output,
    ) as session:
        request = pull_request(opts)
        blocked = _SERVICE.mutating_config_exit_code(request, "pull")
        if blocked is not None:
            if session is not None:
                session.fail("Collect my words blocked by configuration or recovery state.")
            return emit_command_exit(opts, "pull", blocked)
        preview = _SERVICE.prepare_pull(request)
        if not preview.is_executable:
            code = preview.wordlist_error or preview.prepare_error or ExitCode.PUSH_ABORT
            if session is not None:
                session.fail("Collect my words could not start — check the word list and apps.")
            return emit_command_exit(opts, "pull", code)
        execution = _SERVICE.execute_pull(
            request,
            preview,
            confirmed_plan_id=preview.plan_identifier,
            event_sink=session,
        )
        if isinstance(execution.result, ExitCode):
            if session is not None:
                session.fail("Collect my words stopped before completion.")
            return emit_command_exit(opts, "pull", execution.result)
        before, after = execution.result
        _SERVICE.build_pull_report(
            execution,
            duration_ms=session.elapsed_ms if session is not None else 0,
        )
        source = opts.add_from
        from .application.project_resolution import resolve_project_wordlist
        from .cli_request_adapter import project_ref
        from .workspace_git import inspect_workspace_git, workspace_git_dirty_message

        warnings: list[str] = list(preview.warnings)
        wl = resolve_project_wordlist(project_ref(opts))
        # Pull may newly dirty the wordlist; re-check after the write.
        git_status = inspect_workspace_git(wl.parent)
        if git_status is not None and git_status.is_dirty:
            dirty_message = workspace_git_dirty_message(git_status)
            if dirty_message not in warnings:
                warnings.append(dirty_message)
        if opts.json_output:
            emit_json(
                {
                    **base_payload("pull", exit=int(ExitCode.OK)),
                    "before": before,
                    "after": after,
                    "added": after - before,
                    "source": source,
                    "warnings": warnings,
                }
            )
            return int(ExitCode.OK)
        for warning in warnings:
            log.warn(warning)
        done = f"wordlist: {before} -> {after} (+{after - before})"
        if session is not None:
            session.succeed(done)
        else:
            log.done(done)
        return int(ExitCode.OK)


def cmd_push(opts: CliOptions) -> int:
    with quiet_json_output(opts):
        return _cmd_push_via_service(opts)


def _cmd_push_via_service(opts: CliOptions) -> int:
    dry_run = opts.dry_run
    mode = " (dry-run)" if dry_run else ""
    with operation_session(
        OperationSpec(
            key="push",
            title=f"push{mode}: wordlist OVERWRITES all dictionaries",
            descriptions=(UPDATE_APPS_HELP,),
            activity="Update my apps",
        ),
        enabled=not opts.json_output,
    ) as session:
        request = push_request(opts)
        config, _ = load_project_settings_with_issues(wordlist=request.project.wordlist)
        warn_missing_optional_apps(settings=RuntimeSettings.from_config_dict(config))
        blocked = _SERVICE.mutating_config_exit_code(request, "push")
        if blocked is not None:
            if session is not None:
                session.fail("Update my apps blocked by configuration or recovery state.")
            return int(blocked)
        preview = _SERVICE.load_push_preview(request)
        if not preview.is_executable:
            code = preview.wordlist_error or preview.prepare_error or ExitCode.PUSH_ABORT
            return finish_push(code, opts, dry_run=dry_run, command="push", session=session)
        if not dry_run:
            exit_code = guard_exit_code(
                _running_apps_check_for_push(opts, preview),
                cancelled=ExitCode.CANCELLED,
                quiet=opts.json_output,
            )
            if exit_code is not None:
                code = ExitCode(exit_code)
                action = "interrupted" if code is ExitCode.SYNC_INTERRUPTED else "cancelled"
                if session is not None:
                    session.abort("Update my apps cancelled while apps were still open.")
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
                    if session is not None:
                        session.abort("Update my apps cancelled during removal review.")
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
                if session is not None:
                    session.abort("Update my apps cancelled before confirmation.")
                return emit_command_exit(
                    opts,
                    "push",
                    code,
                    dry_run=dry_run,
                    action=action,
                    reason="confirm_push_removals",
                )
        if dry_run:
            if session is not None:
                session.note("Building dry-run preview (no writes).")
            execution = _SERVICE.execute_push_dry_run(request, preview)
        else:
            execution = _SERVICE.execute_push_preview(
                request,
                preview,
                confirmed_plan_id=preview.plan_identifier,
                event_sink=session,
            )
        result = execution.result
        if dry_run and not isinstance(result, ExitCode) and not opts.json_output:
            snapshot = _SERVICE.load_status(status_request(opts))
            for diff in snapshot.diffs:
                print_status_diff(diff, verbose=opts.verbose)
        if not dry_run:
            _SERVICE.build_push_report(
                execution,
                duration_ms=session.elapsed_ms if session is not None else 0,
            )
        return finish_push(
            result,
            opts,
            dry_run=dry_run,
            command="push",
            recovery_required=execution.recovery_required,
            outcome=execution.outcome.value,
            session=session,
        )


def cmd_init(opts: CliOptions) -> int:
    from .paths import resolve_wordlist_path
    from .project_setup.discovery import discover_setup_targets
    from .project_setup.draft import SetupDraft

    with quiet_json_output(opts):
        with operation_session(
            OperationSpec(
                key="init",
                title="init: create wordlist and config from bundled examples",
                descriptions=(
                    "Create a local Spell Sync project folder with wordlist and config file.",
                ),
                activity="Create project",
            ),
            enabled=not opts.json_output,
        ) as session:
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
                # Existing spell-sync.toml is a soft conflict (idempotent re-init).
                # Hard conflicts (missing wordlist without create, non-file path) abort.
                hard_conflicts = tuple(
                    item for item in prepared.conflicts if item != "spell-sync.toml already exists."
                )
                if hard_conflicts:
                    detail = "; ".join(hard_conflicts)
                    if opts.json_output:
                        emit_json(
                            {
                                **base_payload("init", exit=int(ExitCode.PUSH_ABORT)),
                                "created": [],
                                "outcome": "stopped_safely",
                                "reason": "setup_conflict",
                                "detail": detail,
                            }
                        )
                        return int(ExitCode.PUSH_ABORT)
                    if session is not None:
                        session.abort(f"init blocked — {detail}")
                    else:
                        log.abort(f"init blocked — {detail}")
                    return int(ExitCode.PUSH_ABORT)
                if opts.json_output:
                    emit_json(
                        {
                            **base_payload("init", exit=int(ExitCode.OK)),
                            "created": [],
                            "outcome": "stopped_safely",
                        }
                    )
                    return int(ExitCode.OK)
                if session is not None:
                    session.succeed(
                        "nothing to create — wordlist.txt, spell-sync.toml, "
                        "and lint-whitelist.txt already exist."
                    )
                else:
                    log.info(
                        "nothing to create — wordlist.txt, spell-sync.toml, "
                        "and lint-whitelist.txt already exist."
                    )
                return int(ExitCode.OK)
            execution = service.execute_project_setup(
                prepared,
                confirmed_setup_id=prepared.setup_id,
                event_sink=session,
            )
            service.build_setup_report(
                execution,
                duration_ms=session.elapsed_ms if session is not None else 0,
            )
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
                if session is not None:
                    session.fail(execution.message)
                else:
                    log.error(execution.message)
                return exit_code
            details = [f"created {name}" for name in execution.created_files]
            if execution.created_files:
                details.extend(
                    (
                        "next: edit wordlist.txt, then spell-sync pull or spell-sync push",
                        "optional: keep the folder local, in a synced cloud directory, "
                        "or a private Git remote — see docs/PERSONAL_WORKSPACE.md",
                    )
                )
            if session is not None:
                if execution.created_files:
                    session.succeed("project files created", details=details)
                else:
                    session.succeed("nothing to create — project files already exist.")
            else:
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
    from .command_helpers import wordlist_file_for

    with quiet_json_output(opts):
        return _cmd_lint_locked(opts, wordlist_file_for(opts))


def _cmd_lint_locked(opts: CliOptions, wordlist) -> int:
    from .command_helpers import mutating_command_scope

    mode = " (fix)" if opts.fix else ""
    with operation_session(
        OperationSpec(
            key="lint",
            title=f"lint{mode}: check word list quality",
            descriptions=(
                "Scan the personal word list for duplicates, sort order, and other issues.",
            ),
            activity="Lint word list",
        ),
        enabled=not opts.json_output,
    ) as session:
        if opts.fix:
            with mutating_command_scope(opts, "lint") as scope:
                if isinstance(scope, int):
                    if session is not None:
                        session.fail("Lint --fix blocked by configuration or recovery state.")
                    return int(scope)
                return _finish_lint(opts, wordlist, session)
        return _finish_lint(opts, wordlist, session)


def _finish_lint(opts: CliOptions, wordlist, session) -> int:
    if session is not None:
        session.note("Scanning word list.")
    code = run_lint(
        wordlist,
        fix=opts.fix,
        strict=opts.strict,
        own_outcome=session is None,
    )
    if opts.json_output:
        emit_json(base_payload("lint", exit=int(code)))
        return int(code)
    if session is None:
        return int(code)
    if int(code) == int(ExitCode.OK):
        session.succeed("lint finished")
    elif int(code) == int(ExitCode.WORDLIST_UNREADABLE):
        session.abort("lint stopped — word list could not be read")
    elif int(code) == int(ExitCode.PUSH_ABORT):
        session.fail("lint --fix could not write the word list")
    elif int(code) == int(ExitCode.LINT_FAILED):
        session.fail("lint found issues that need attention")
    else:
        session.fail("lint stopped before completion")
    return int(code)
