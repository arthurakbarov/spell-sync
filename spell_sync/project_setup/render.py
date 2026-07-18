"""Render typed project configuration to canonical TOML bytes."""

from __future__ import annotations

from .draft import ProjectConfigDraft

_ALL_DICTIONARY_FLAGS = (
    "editors",
    "chrome",
    "edge",
    "brave",
    "vivaldi",
    "firefox",
    "neovim",
    "jetbrains",
    "hunspell",
    "obsidian",
    "libreoffice",
)


def render_project_config(draft: ProjectConfigDraft) -> bytes:
    enabled = set(draft.enabled_targets)
    lines = ["[dictionaries]"]
    for name in _ALL_DICTIONARY_FLAGS:
        lines.append(f"{name} = {'true' if name in enabled else 'false'}")
    lines.extend(
        [
            "",
            "[push]",
            f"guard_wordlist_max = {10}",
            f"guard_local_min = {20}",
            "",
            "[io]",
            f"backup_keep = {draft.safety.backup_keep}",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")
