"""Resolve application requests into runtime inputs (Phase 2B boundary helper)."""

from __future__ import annotations

from pathlib import Path

from ..config import push_strict_enabled
from ..paths import resolve_wordlist_path
from ..settings import push_flag
from ..sync_context import RuntimeConfig
from .requests import ProjectRef, PushRequest


def resolve_project_wordlist(project: ProjectRef) -> Path:
    """Resolve effective wordlist path using standard project rules."""
    if project.wordlist is None:
        return resolve_wordlist_path(None)
    return resolve_wordlist_path(str(project.wordlist))


def effective_push_strict(
    request: PushRequest,
    *,
    config: RuntimeConfig | None = None,
) -> bool:
    """Resolve Push strict mode from request override or explicit runtime config."""
    if request.strict_override is not None:
        return request.strict_override
    if config is not None:
        return push_flag("strict", False, settings=config)
    return push_strict_enabled()
