"""Render typed project configuration to canonical TOML bytes."""

from __future__ import annotations

from typing import Any

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
    "macos_spelling",
    "win_spelling",
)


def _push_int(existing: dict[str, dict[str, Any]] | None, key: str, default: int) -> int:
    if existing is None:
        return default
    value = existing.get("push", {}).get(key)
    if isinstance(value, int):
        return value
    return default


def _push_bool(existing: dict[str, dict[str, Any]] | None, key: str, default: bool) -> bool:
    if existing is None:
        return default
    value = existing.get("push", {}).get(key)
    if isinstance(value, bool):
        return value
    return default


def _io_int(existing: dict[str, dict[str, Any]] | None, key: str, default: int) -> int:
    if existing is None:
        return default
    value = existing.get("io", {}).get(key)
    if isinstance(value, int):
        return value
    return default


def render_project_config(
    draft: ProjectConfigDraft,
    *,
    existing_config: dict[str, dict[str, Any]] | None = None,
) -> bytes:
    enabled = set(draft.enabled_targets)
    lines = ["[dictionaries]"]
    for name in _ALL_DICTIONARY_FLAGS:
        lines.append(f"{name} = {'true' if name in enabled else 'false'}")
    lines.append("")
    lines.append("[push]")
    lines.append(f"guard_wordlist_max = {_push_int(existing_config, 'guard_wordlist_max', 10)}")
    lines.append(f"guard_local_min = {_push_int(existing_config, 'guard_local_min', 20)}")
    if existing_config is not None:
        strict = _push_bool(existing_config, "strict", False)
        lines.append(f"strict = {'true' if strict else 'false'}")
        max_removals = existing_config.get("push", {}).get("max_removals_without_confirm")
        if isinstance(max_removals, int):
            lines.append(f"max_removals_without_confirm = {max_removals}")
    lines.append("")
    lines.append("[io]")
    backup_keep = _io_int(existing_config, "backup_keep", draft.safety.backup_keep)
    lines.append(f"backup_keep = {backup_keep}")
    if existing_config is not None:
        neovim = existing_config.get("neovim", {})
        mkspell = neovim.get("mkspell_after_push")
        if isinstance(mkspell, bool):
            lines.extend(["", "[neovim]", f"mkspell_after_push = {'true' if mkspell else 'false'}"])
    lines.append("")
    return "\n".join(lines).encode("utf-8")
