"""Sublime Text Preferences helpers (User override vs SpellSync package)."""

from __future__ import annotations

import json
from pathlib import Path

from .paths import sublime_packages_dir


def sublime_user_preferences_path(*, packages_dir: Path | None = None) -> Path:
    root = packages_dir if packages_dir is not None else sublime_packages_dir()
    return root / "User" / "Preferences.sublime-settings"


def _strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments without touching string contents (e.g. https://)."""
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    escape = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            i += 2
            while i < n and text[i] not in "\r\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i = min(i + 2, n)
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _strip_trailing_commas(text: str) -> str:
    """Drop commas before } or ] outside of strings."""
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    escape = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == ",":
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] in "}]":
                i += 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _load_preferences_object(path: Path) -> dict[str, object] | None:
    if not path.is_file() and not path.is_symlink():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return None
    for candidate in (text, _strip_trailing_commas(_strip_jsonc(text))):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def user_added_words_override_count(*, packages_dir: Path | None = None) -> int:
    """Count non-empty User Preferences ``added_words`` entries.

    Returns ``-1`` when the ``added_words`` key is present as a list but contains
    no usable strings (empty list still overrides the SpellSync package layer in
    Sublime). Returns ``0`` when the key is absent or unreadable.
    """
    path = sublime_user_preferences_path(packages_dir=packages_dir)
    data = _load_preferences_object(path)
    if data is None or "added_words" not in data:
        return 0
    added = data.get("added_words")
    if not isinstance(added, list):
        return 0
    count = sum(1 for item in added if isinstance(item, str) and item.strip())
    return count if count > 0 else -1


def user_added_words_override_message(*, packages_dir: Path | None = None) -> str | None:
    count = user_added_words_override_count(packages_dir=packages_dir)
    if count == 0:
        return None
    if count < 0:
        return (
            "Sublime Text User Preferences define added_words (empty), which overrides "
            "the SpellSync package dictionary. "
            "Remove added_words from User Preferences so Update my apps can affect the editor."
        )
    return (
        "Sublime Text User Preferences define added_words "
        f"({count}), which overrides the SpellSync package dictionary. "
        "Remove added_words from User Preferences so Update my apps can affect the editor."
    )
