"""Shell-like filesystem path listing and completion for TUI path pickers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_WORDLIST_NAME = "wordlist.txt"
_DEFAULT_LIMIT = 60


@dataclass(frozen=True, slots=True)
class PathCompletion:
    """One completion row: prompt for the list, value for the Input."""

    prompt: str
    value: str


def _home_style(typed: str) -> bool:
    return typed == "~" or typed.startswith("~/") or typed.startswith("~" + os.sep)


def _format_value(typed: str, completed: Path, *, directory: bool) -> str:
    home = Path.home()
    try:
        relative = completed.relative_to(home)
        use_home = _home_style(typed) or not typed.strip()
    except ValueError:
        relative = None
        use_home = False
    if use_home and relative is not None:
        text = "~/" + relative.as_posix() if str(relative) != "." else "~/"
    else:
        text = completed.as_posix() if os.sep == "/" else str(completed)
    if directory and not text.endswith("/"):
        text += "/"
    return text


def _listing_context(typed: str) -> tuple[Path, str, str]:
    """Return (directory to list, name prefix, typed string used for formatting)."""
    raw = typed.strip()
    if not raw:
        return Path.home(), "", "~/"
    if raw == "~":
        return Path.home(), "", "~/"
    if raw.endswith(("/", "\\")):
        directory = Path(raw).expanduser()
        return directory, "", raw if raw.endswith("/") else raw.replace("\\", "/") + "/"
    expanded = Path(raw).expanduser()
    return expanded.parent, expanded.name, raw


def list_path_completions(
    typed: str,
    *,
    limit: int = _DEFAULT_LIMIT,
) -> list[PathCompletion]:
    """List matching path completions for a typed value.

    - Empty / ``~``: entries under the home directory.
    - Trailing ``/``: all entries in that directory (no first letter required).
    - Partial segment: filter by prefix (case-insensitive fallback).
    Directories come first (with trailing ``/``), then ``wordlist.txt``, then other files.
    """
    directory, prefix, format_typed = _listing_context(typed)
    if not directory.exists() or not directory.is_dir():
        return []
    try:
        names = os.listdir(directory)
    except OSError:
        return []

    def matches(name: str) -> bool:
        if not prefix:
            return True
        return name.startswith(prefix) or name.casefold().startswith(prefix.casefold())

    dirs: list[str] = []
    files: list[str] = []
    for name in sorted(names, key=str.casefold):
        if name in {".", ".."} or not matches(name):
            continue
        # Hide dotfiles unless the user typed a leading dot.
        if name.startswith(".") and not prefix.startswith("."):
            continue
        path = directory / name
        try:
            is_dir = path.is_dir()
        except OSError:
            continue
        if is_dir:
            dirs.append(name)
        else:
            files.append(name)

    if prefix:
        exact_dirs = [n for n in dirs if n.startswith(prefix)]
        exact_files = [n for n in files if n.startswith(prefix)]
        if exact_dirs or exact_files:
            dirs = exact_dirs or dirs
            files = exact_files or files

    wordlists = [n for n in files if n.lower() == _WORDLIST_NAME]
    other_files = [n for n in files if n.lower() != _WORDLIST_NAME]
    ordered = dirs + wordlists + other_files

    completions: list[PathCompletion] = []
    for name in ordered[:limit]:
        path = directory / name
        is_dir = name in dirs
        value = _format_value(format_typed, path, directory=is_dir)
        prompt = f"{name}/" if is_dir else name
        completions.append(PathCompletion(prompt=prompt, value=value))
    return completions


def complete_path(value: str) -> str | None:
    """Best single completion (first list hit), for optional inline suggestion."""
    hits = list_path_completions(value, limit=1)
    return hits[0].value if hits else None
