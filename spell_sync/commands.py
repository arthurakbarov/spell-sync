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
from .application.product_concepts import (
    COLLECT_WORDS_HELP,
    EMPTY_WORDLIST_WARN,
    INIT_CLI_TITLE,
    INIT_DESCRIPTION,
    UPDATE_APPS_HELP,
    format_pull_word_count_line,
)
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
from .dictionary_hints import log_skipped_optional_app_details
from .exit_codes import ExitCode
from .guest_messages import (
    ADD_NEXT_HINT,
    INIT_ALREADY_EXISTS,
    INIT_NEXT_HINT,
    INIT_STORAGE_HINT,
    PARTIAL_PULL_SKIPPED,
    WORD_LIST_NOT_FOUND,
    WORD_LIST_UNREADABLE,
    WORD_LIST_WRITE_FAILED,
    already_present_detail,
    skipped_words_detail,
)
from .io import wordlist_unreadable
from .json_output import base_payload, dictionary_diff_payload, emit_json
from .lint import run_lint
from .log import log
from .operation_presenter import OperationSession, OperationSpec, operation_session
from .removal_review import review_removals_for_preview
from .runtime import installed_package_version
from .runtime_settings import RuntimeSettings
from .sync_run import dictionary_diffs_from_prepared

_SERVICE = SpellSyncService()


def _running_apps_check_for_push(opts: CliOptions, preview) -> bool | None:
    interactive = sys.stdin.isatty() and not opts.yes and not opts.json_output
    prepared = preview.prepared
    settings = prepared.ctx.settings if prepared is not None else None
    if settings is None:
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
                _note(EMPTY_WORDLIST_WARN)
            elif snapshot.destructive_risk:
                _note(snapshot.destructive_risk)
            for message in snapshot.honesty_warnings:
                _note(message)
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
                session.succeed(
                    f"status: {len(snapshot.diffs)} application dictionary(ies) compared"
                )
            return int(ExitCode.OK)


def cmd_pull(opts: CliOptions) -> int:
    with quiet_json_output(opts):
        return _cmd_pull_via_service(opts)


def _cmd_pull_via_service(opts: CliOptions) -> int:
    if opts.add_from:
        title = f"pull: merge words from {opts.add_from} into your word list"
    else:
        title = "pull: collect words from apps into your word list"
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
        from .workspace_git import inspect_workspace_git, workspace_git_dirty_message

        warnings: list[str] = list(preview.warnings)
        # Pull may newly dirty the wordlist; re-check after the write.
        git_status = inspect_workspace_git(Path(preview.wordlist_path).parent)
        if git_status is not None and git_status.is_dirty:
            dirty_message = workspace_git_dirty_message(git_status)
            if dirty_message not in warnings:
                warnings.append(dirty_message)
        partial = bool(preview.sources_skipped)
        exit_code = ExitCode.PARTIAL_PUSH if partial else ExitCode.OK
        if opts.json_output:
            emit_json(
                {
                    **base_payload("pull", exit=int(exit_code)),
                    "before": before,
                    "after": after,
                    "added": after - before,
                    "source": source,
                    "warnings": warnings,
                    "partial": partial,
                    "sources_skipped": list(preview.sources_skipped),
                }
            )
            return int(exit_code)
        for warning in warnings:
            log.warn(warning)
        done = format_pull_word_count_line(
            before,
            after,
            skipped_sources=len(preview.sources_skipped) if partial else 0,
        )
        if session is not None:
            if partial:
                session.succeed(done)
                log.detail(PARTIAL_PULL_SKIPPED)
            else:
                session.succeed(done)
        else:
            log.done(done)
            if partial:
                log.detail(PARTIAL_PULL_SKIPPED)
        return int(exit_code)


def cmd_push(opts: CliOptions) -> int:
    with quiet_json_output(opts):
        return _cmd_push_via_service(opts)


def _cmd_push_via_service(opts: CliOptions) -> int:
    dry_run = opts.dry_run
    mode = " (dry-run)" if dry_run else ""
    with operation_session(
        OperationSpec(
            key="push",
            title=f"push{mode}: update app dictionaries from your word list",
            descriptions=(UPDATE_APPS_HELP,),
            activity="Update my apps",
        ),
        enabled=not opts.json_output,
    ) as session:
        request = push_request(opts)
        blocked = _SERVICE.mutating_config_exit_code(request, "push")
        if blocked is not None:
            if session is not None:
                session.fail("Update my apps blocked by configuration or recovery state.")
            return int(blocked)
        preview = _SERVICE.load_push_preview(request)
        if not preview.is_executable:
            code = preview.wordlist_error or preview.prepare_error or ExitCode.PUSH_ABORT
            return finish_push(code, opts, dry_run=dry_run, command="push", session=session)
        prepared = preview.prepared
        if prepared is not None:
            log_skipped_optional_app_details(settings=prepared.ctx.settings)
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
            prepared = preview.prepared
            if prepared is not None:
                for diff in dictionary_diffs_from_prepared(prepared, verbose=opts.verbose):
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
            warnings=preview.warnings,
            wordlist=prepared.ctx.wordlist if prepared is not None else None,
        )


def cmd_init(opts: CliOptions) -> int:
    from .paths import resolve_wordlist_path
    from .project_setup.discovery import discover_setup_targets
    from .project_setup.draft import SetupDraft

    with quiet_json_output(opts):
        with operation_session(
            OperationSpec(
                key="init",
                title=INIT_CLI_TITLE,
                descriptions=(INIT_DESCRIPTION,),
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
                    session.succeed(INIT_ALREADY_EXISTS)
                else:
                    log.info(INIT_ALREADY_EXISTS)
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
                        INIT_NEXT_HINT,
                        INIT_STORAGE_HINT,
                    )
                )
            if session is not None:
                if execution.created_files:
                    session.succeed("project files created", details=details)
                else:
                    session.succeed(INIT_ALREADY_EXISTS)
            else:
                for name in execution.created_files:
                    log.done(f"created {name}")
                if not execution.created_files:
                    log.info(INIT_ALREADY_EXISTS)
                else:
                    log.info(INIT_NEXT_HINT)
                    log.info(INIT_STORAGE_HINT)
            return exit_code


def cmd_lint(opts: CliOptions) -> int:
    from .command_helpers import mutating_command_scope, wordlist_file_for

    with quiet_json_output(opts):
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
                    return _finish_lint(opts, scope.context.wordlist, session)
            return _finish_lint(opts, wordlist_file_for(opts), session)


def _finish_lint(opts: CliOptions, wordlist, session: OperationSession | None) -> int:
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


def cmd_add(opts: CliOptions) -> int:
    """Add words to wordlist.txt (CLI first-win path)."""
    from .application.project_resolution import resolve_project_wordlist
    from .application.wordlist_edit import append_words_guarded
    from .cli_request_adapter import project_ref

    if not opts.add_words:
        log.error("usage: spell-sync add WORD [WORD...]")
        log.info("Run `spell-sync add --help` for usage.")
        return emit_command_exit(opts, "add", ExitCode.LINT_FAILED, message="missing WORD")
    with quiet_json_output(opts):
        with operation_session(
            OperationSpec(
                key="add",
                title="add: personal words to the word list",
                descriptions=("Append personal words to wordlist.txt without changing apps.",),
                activity="Add words to my list",
            ),
            enabled=not opts.json_output,
        ) as session:
            wordlist = resolve_project_wordlist(project_ref(opts))
            if not wordlist.is_file():
                if session is not None:
                    session.fail(WORD_LIST_NOT_FOUND)
                log.error(WORD_LIST_NOT_FOUND)
                log.info("Run `spell-sync init` or open the TUI Start here flow first.")
                return emit_command_exit(
                    opts,
                    "add",
                    ExitCode.WORDLIST_UNREADABLE,
                    message=WORD_LIST_NOT_FOUND,
                    wordlist=str(wordlist),
                )
            raw = "\n".join(opts.add_words)
            try:
                result = append_words_guarded(wordlist, raw, json_output=opts.json_output)
            except FileNotFoundError:
                if session is not None:
                    session.fail(WORD_LIST_NOT_FOUND)
                log.error(WORD_LIST_NOT_FOUND)
                return emit_command_exit(
                    opts,
                    "add",
                    ExitCode.WORDLIST_UNREADABLE,
                    message=WORD_LIST_NOT_FOUND,
                    wordlist=str(wordlist),
                )
            except OSError:
                if wordlist_unreadable(wordlist):
                    if session is not None:
                        session.fail(WORD_LIST_UNREADABLE)
                    log.error(WORD_LIST_UNREADABLE)
                    return emit_command_exit(
                        opts,
                        "add",
                        ExitCode.WORDLIST_UNREADABLE,
                        message=WORD_LIST_UNREADABLE,
                        wordlist=str(wordlist),
                    )
                if session is not None:
                    session.fail(WORD_LIST_WRITE_FAILED)
                log.error(WORD_LIST_WRITE_FAILED)
                return emit_command_exit(
                    opts,
                    "add",
                    ExitCode.PUSH_ABORT,
                    message=WORD_LIST_WRITE_FAILED,
                    wordlist=str(wordlist),
                )
            if isinstance(result, int):
                if session is not None:
                    session.fail("Add words blocked by configuration or recovery state.")
                return emit_command_exit(
                    opts,
                    "add",
                    ExitCode(result),
                    message="add blocked by configuration or recovery state",
                    wordlist=str(wordlist),
                )
            payload = {
                "wordlist": str(wordlist),
                "added": list(result.added),
                "already_present": list(result.already_present),
                "rejected": list(result.rejected),
            }
            if not result.had_usable_input:
                if session is not None:
                    session.fail("No usable words")
                log.warn("No usable words (empty or could not be used).")
                for line in result.detail_lines():
                    log.warn(line)
                return emit_command_exit(
                    opts,
                    "add",
                    ExitCode.LINT_FAILED,
                    message="no usable words",
                    **payload,
                )

            def _log_add_follow_up() -> None:
                if result.already_present:
                    log.info(already_present_detail(result.already_present))
                if result.rejected:
                    log.warn(skipped_words_detail(result.rejected))
                log.info(ADD_NEXT_HINT)

            if result.added_count:
                if session is not None:
                    session.succeed(f"Added {result.added_count} word(s)")
                else:
                    log.done(f"Added {result.added_count} word(s) to the personal word list.")
                _log_add_follow_up()
                return emit_command_exit(opts, "add", ExitCode.OK, **payload)
            if session is not None:
                session.succeed("No new words added")
            log.warn("No new words added (already present).")
            _log_add_follow_up()
            return emit_command_exit(opts, "add", ExitCode.OK, **payload)
