"""Environment inspection helpers for health reports."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from ..runtime import cli_argv, discover_pip_script, path_export_for_script
from .types import CliStatus, DoctorCheck, GitHooksStatus

# Markers from the current personal-workspace hook templates.
_PRE_PUSH_CURRENT_MARKERS = ("spell_sync_personal_paths", "spell-sync.guard")
_PRE_COMMIT_CURRENT_MARKERS = ("lint staged", 'git show ":')


def inspect_cli() -> CliStatus:
    executable = shutil.which("spell-sync")
    pip_script_path = discover_pip_script()
    pip_script = str(pip_script_path) if pip_script_path else None
    path_export = path_export_for_script(pip_script_path) if pip_script_path is not None else None
    return CliStatus(
        on_path=executable is not None,
        argv=tuple(cli_argv()),
        executable=executable,
        pip_script=pip_script,
        path_export=path_export,
    )


def _hook_missing_markers(path: Path, markers: tuple[str, ...]) -> bool:
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return True
    return any(marker not in text for marker in markers)


def inspect_git_hooks(hooks_dir: Path) -> GitHooksStatus | None:
    if not hooks_dir.is_dir():
        return None
    pre_push_path = hooks_dir / "pre-push"
    pre_commit_path = hooks_dir / "pre-commit"
    pre_push = pre_push_path.is_file() and os.access(pre_push_path, os.X_OK)
    pre_commit = pre_commit_path.is_file() and os.access(pre_commit_path, os.X_OK)
    pre_push_stale = False
    if pre_push_path.is_file():
        pre_push_stale = _hook_missing_markers(pre_push_path, _PRE_PUSH_CURRENT_MARKERS)
    elif pre_push:
        pre_push_stale = True
    pre_commit_stale = False
    if pre_commit_path.is_file():
        pre_commit_stale = _hook_missing_markers(pre_commit_path, _PRE_COMMIT_CURRENT_MARKERS)
    elif pre_commit:
        pre_commit_stale = True
    return GitHooksStatus(
        pre_push=pre_push,
        pre_commit=pre_commit,
        pre_push_stale=pre_push_stale,
        pre_commit_stale=pre_commit_stale,
    )


def git_hooks_checks(status: GitHooksStatus) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    missing = [
        name
        for name, installed in (
            ("pre-push", status.pre_push),
            ("pre-commit", status.pre_commit),
        )
        if not installed
    ]
    if missing:
        checks.append(
            DoctorCheck(
                "info",
                f"Git hooks incomplete (missing {', '.join(missing)}). "
                "Install git hooks in your wordlist repository.",
            ),
        )
    if status.pre_push_stale:
        checks.append(
            DoctorCheck(
                "warn",
                "pre-push hook is outdated — reinstall git hooks in your wordlist repository.",
            ),
        )
    if status.pre_commit_stale:
        checks.append(
            DoctorCheck(
                "warn",
                "pre-commit hook is outdated — reinstall git hooks in your wordlist repository.",
            ),
        )
    return checks
