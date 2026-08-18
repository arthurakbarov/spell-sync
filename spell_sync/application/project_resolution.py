"""Resolve application requests into runtime inputs."""

from pathlib import Path

from ..paths import resolve_wordlist_path
from ..runtime_settings import RuntimeSettings
from .requests import ProjectRef, PushRequest


def resolve_project_wordlist(project: ProjectRef) -> Path:
    """Resolve effective wordlist path using standard project rules."""
    if project.wordlist is None:
        return resolve_wordlist_path(None)
    return resolve_wordlist_path(str(project.wordlist))


def effective_push_strict(
    request: PushRequest,
    *,
    settings: RuntimeSettings | None = None,
) -> bool:
    """Resolve Push strict mode from request override or explicit runtime settings."""
    if request.strict_override is not None:
        return request.strict_override
    if settings is not None:
        return settings.push.strict
    raise ValueError("explicit runtime settings required for push strict mode")
