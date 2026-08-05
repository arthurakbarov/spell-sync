"""Filesystem path completion for TUI Input widgets (shell-like)."""

from __future__ import annotations

import os
from pathlib import Path

from textual.suggester import Suggester

_WORDLIST_NAME = "wordlist.txt"


def _preserve_home_prefix(typed: str, completed: Path) -> str:
    """Keep a leading ~/ in the suggestion when the user typed one."""
    home = Path.home()
    try:
        relative = completed.relative_to(home)
    except ValueError:
        return str(completed)
    if typed == "~" or typed.startswith("~/") or typed.startswith("~" + os.sep):
        return "~/" + relative.as_posix()
    return str(completed)


def complete_path(value: str) -> str | None:
    """Return one shell-style completion for ``value``, or None.

    Completes the last path segment against entries in the parent directory.
    Directories are suggested with a trailing ``/``; ``wordlist.txt`` is
    preferred when the prefix matches.
    """
    if not value or value.isspace() or value.endswith(("/", "\\")):
        return None

    typed = value
    expanded = Path(typed).expanduser()
    parent = expanded.parent
    prefix = expanded.name
    if not parent.exists() or not parent.is_dir():
        return None
    try:
        names = sorted(os.listdir(parent))
    except OSError:
        return None

    def _match(name: str) -> bool:
        if not prefix:
            return True
        return name.startswith(prefix) or name.casefold().startswith(prefix.casefold())

    directories: list[str] = []
    files: list[str] = []
    for name in names:
        if not _match(name):
            continue
        path = parent / name
        try:
            is_dir = path.is_dir()
        except OSError:
            continue
        if is_dir:
            directories.append(name)
        else:
            files.append(name)

    # Prefer exact-case matches when both exist.
    def _prefer_exact(candidates: list[str]) -> list[str]:
        exact = [n for n in candidates if n.startswith(prefix)]
        return exact or candidates

    directories = _prefer_exact(directories)
    files = _prefer_exact(files)

    wordlist_hits = [n for n in files if n.lower() == _WORDLIST_NAME]
    if wordlist_hits:
        return _preserve_home_prefix(typed, parent / wordlist_hits[0])

    if directories:
        text = _preserve_home_prefix(typed, parent / directories[0])
        return text if text.endswith("/") else text + "/"

    if files:
        return _preserve_home_prefix(typed, parent / files[0])
    return None


class PathSuggester(Suggester):
    """Inline path suggestions for Textual Input (accept with → or Tab)."""

    def __init__(self) -> None:
        super().__init__(use_cache=False, case_sensitive=True)

    async def get_suggestion(self, value: str) -> str | None:
        return complete_path(value)
