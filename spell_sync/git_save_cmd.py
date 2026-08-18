"""Commit (and optionally push) personal wordlist Git changes."""

from __future__ import annotations

import sys

from .cli_options import CliOptions
from .command_helpers import quiet_json_output, wordlist_file_for
from .exit_codes import ExitCode
from .guest_messages import WORD_LIST_UNREADABLE
from .io import wordlist_unreadable
from .json_output import base_payload, emit_json
from .keymap import is_confirmed
from .log import log
from .operation_presenter import OperationSession, OperationSpec, operation_session
from .workspace_git import (
    WorkspaceGitStatus,
    commit_personal_workspace,
    inspect_workspace_git,
    push_personal_workspace,
    workspace_git_dirty_message,
)

_DEFAULT_MESSAGE = "Update personal Spell Sync word list"


def _confirm(prompt: str, *, opts: CliOptions) -> bool | None:
    """Return True/False, or None when non-interactive without --yes."""
    if opts.yes:
        return True
    if opts.json_output or not sys.stdin.isatty():
        return None
    return is_confirmed(input(prompt))


def _fail(
    opts: CliOptions,
    session: OperationSession | None,
    *,
    code: ExitCode,
    message: str,
    payload: dict[str, object] | None = None,
) -> int:
    body = payload or {}
    if opts.json_output:
        emit_json(
            {
                **base_payload("git-save", exit=int(code)),
                "message": message,
                **body,
            }
        )
        return int(code)
    if session is not None:
        if code is ExitCode.CANCELLED:
            session.abort(message)
        else:
            session.fail(message)
    else:
        log.abort(message)
    return int(code)


def cmd_git_save(opts: CliOptions) -> int:
    with quiet_json_output(opts):
        with operation_session(
            OperationSpec(
                key="git-save",
                title="git-save: commit personal word list changes",
                descriptions=(
                    "Commit wordlist.txt and spell-sync.toml in the personal workspace Git repo.",
                ),
                activity="Save word list to Git",
            ),
            enabled=not opts.json_output,
        ) as session:
            wordlist = wordlist_file_for(opts)
            if not wordlist.is_file():
                return _fail(
                    opts,
                    session,
                    code=ExitCode.PUSH_ABORT,
                    message="no word list project found",
                    payload={
                        "git_repo": False,
                        "dirty": False,
                        "committed": False,
                        "pushed": False,
                    },
                )
            if wordlist_unreadable(wordlist):
                return _fail(
                    opts,
                    session,
                    code=ExitCode.WORDLIST_UNREADABLE,
                    message=WORD_LIST_UNREADABLE,
                    payload={
                        "git_repo": False,
                        "dirty": False,
                        "committed": False,
                        "pushed": False,
                    },
                )

            project_dir = wordlist.parent
            status = inspect_workspace_git(project_dir)
            if status is None:
                return _finish(
                    opts,
                    session,
                    message="personal workspace is not a Git repository (or git is unavailable)",
                    payload={
                        "git_repo": False,
                        "dirty": False,
                        "committed": False,
                        "pushed": False,
                    },
                )

            committed = False
            if status.is_dirty:
                log.info(workspace_git_dirty_message(status))
                for path in status.dirty_relpaths:
                    log.detail(f"  {path}")
                choice = _confirm("Commit these files? [y/N] ", opts=opts)
                if choice is None:
                    return _fail(
                        opts,
                        session,
                        code=ExitCode.CANCELLED,
                        message="git-save requires --yes in non-interactive mode",
                        payload={
                            "git_repo": True,
                            "dirty": True,
                            "committed": False,
                            "pushed": False,
                        },
                    )
                if not choice:
                    return _fail(
                        opts,
                        session,
                        code=ExitCode.CANCELLED,
                        message="git-save cancelled",
                        payload={
                            "git_repo": True,
                            "dirty": True,
                            "committed": False,
                            "pushed": False,
                        },
                    )

                message = (opts.git_message or "").strip() or _DEFAULT_MESSAGE
                ok, detail = commit_personal_workspace(status, message=message)
                if not ok:
                    hint = detail
                    if "lint" in detail.lower() or "pre-commit" in detail.lower():
                        hint = f"{detail} (Git hooks blocked the commit — fix lint or adjust hooks)"
                    return _fail(
                        opts,
                        session,
                        code=ExitCode.PUSH_ABORT,
                        message=f"git commit failed: {hint}",
                        payload={
                            "git_repo": True,
                            "dirty": True,
                            "committed": False,
                            "pushed": False,
                        },
                    )
                committed = True
                status = inspect_workspace_git(project_dir) or status
            elif not opts.push_remote:
                return _finish(
                    opts,
                    session,
                    message="personal workspace Git is clean (wordlist.txt / spell-sync.toml)",
                    payload={
                        "git_repo": True,
                        "dirty": False,
                        "committed": False,
                        "pushed": False,
                    },
                )

            pushed = False
            push_skip_reason = ""
            if opts.push_remote:
                outcome, detail = _run_push(opts, status)
                if outcome == "need_yes":
                    return _fail(
                        opts,
                        session,
                        code=ExitCode.CANCELLED,
                        message="git-save --push requires --yes in non-interactive mode",
                        payload={
                            "git_repo": True,
                            "dirty": False,
                            "committed": committed,
                            "pushed": False,
                        },
                    )
                if outcome == "failed":
                    return _fail(
                        opts,
                        session,
                        code=ExitCode.PUSH_ABORT,
                        message=f"git push failed: {detail}",
                        payload={
                            "git_repo": True,
                            "dirty": False,
                            "committed": committed,
                            "pushed": False,
                        },
                    )
                pushed = outcome == "pushed"
                if outcome == "skipped":
                    push_skip_reason = detail

            parts: list[str] = []
            if committed:
                parts.append("committed")
            elif not opts.push_remote:
                parts.append("clean")
            if opts.push_remote:
                parts.append("pushed" if pushed else "push skipped")
            payload: dict[str, object] = {
                "git_repo": True,
                "dirty": False,
                "committed": committed,
                "pushed": pushed,
            }
            if push_skip_reason:
                payload["push_skipped_reason"] = push_skip_reason
            return _finish(
                opts,
                session,
                message=f"git-save: {', '.join(parts)}",
                payload=payload,
            )


def _run_push(opts: CliOptions, status: WorkspaceGitStatus) -> tuple[str, str]:
    if not status.has_upstream:
        detail = "no upstream configured — set upstream once: git push -u origin HEAD"
        log.warn(detail)
        return "skipped", detail
    choice = _confirm("Push to upstream? [y/N] ", opts=opts)
    if choice is None:
        return "need_yes", ""
    if not choice:
        return "skipped", "push declined"
    ok, detail = push_personal_workspace(status)
    if not ok:
        return "failed", detail
    return "pushed", ""


def _finish(
    opts: CliOptions,
    session: OperationSession | None,
    *,
    message: str,
    payload: dict[str, object],
) -> int:
    if opts.json_output:
        emit_json({**base_payload("git-save", exit=int(ExitCode.OK)), **payload})
        return int(ExitCode.OK)
    if session is not None:
        session.succeed(message)
    else:
        log.done(message)
    return int(ExitCode.OK)
