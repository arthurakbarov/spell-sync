"""Resolve application requests into runtime inputs (Phase 2B boundary helper)."""

from __future__ import annotations

from pathlib import Path

from ..config import push_strict_enabled
from ..paths import resolve_wordlist_path
from .requests import ProjectRef, PushRequest


def resolve_project_wordlist(project: ProjectRef) -> Path:
    """Resolve effective wordlist path using standard project rules."""
    if project.wordlist is None:
        return resolve_wordlist_path(None)
    return resolve_wordlist_path(str(project.wordlist))


def effective_push_strict(request: PushRequest) -> bool:
    """Resolve Push strict mode; reads implicit settings until Phase 3 explicit runtime."""
    if request.strict_override is not None:
        return request.strict_override
    return push_strict_enabled()
