"""Actionable next steps derived from a health report."""

from __future__ import annotations

from ..paths import is_macos
from .types import CliStatus, DoctorAction, GitHooksStatus


def build_doctor_actions(
    *,
    skipped_unreadable: tuple[str, ...],
    git_hooks: GitHooksStatus | None,
    cli_status: CliStatus,
    unfinished_journal: bool = False,
) -> tuple[DoctorAction, ...]:
    actions: list[DoctorAction] = []
    if unfinished_journal:
        actions.append(
            DoctorAction(
                id="recover-push",
                reason="unfinished push journal",
                command="spell-sync recover",
            ),
        )
    if not cli_status.on_path and cli_status.path_export:
        actions.append(
            DoctorAction(
                id="path-export",
                reason="spell-sync not on PATH",
                shell=cli_status.path_export,
            ),
        )
    if is_macos() and any("applespell" in name.lower() for name in skipped_unreadable):
        actions.append(
            DoctorAction(
                id="macos-fda",
                reason="macos-applespell unreadable",
                hint="System Settings → Privacy & Security → Full Disk Access for Terminal",
                optional=True,
            ),
        )
    if git_hooks is not None:
        if git_hooks.pre_push_stale:
            actions.append(
                DoctorAction(
                    id="reinstall-hooks",
                    reason="pre-push hook outdated",
                    hint="install git hooks in your wordlist repository",
                ),
            )
        missing = [
            name
            for name, installed in (
                ("pre-push", git_hooks.pre_push),
                ("pre-commit", git_hooks.pre_commit),
            )
            if not installed
        ]
        if missing:
            actions.append(
                DoctorAction(
                    id="install-hooks",
                    reason=f"missing {', '.join(missing)}",
                    hint="install git hooks in your wordlist repository",
                ),
            )
    return tuple(actions)
