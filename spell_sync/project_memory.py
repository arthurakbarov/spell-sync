"""Machine-local active wordlist pointer and recent list (not project config).

Stored under the same state directory as operation history. Paths are absolute.
Corrupt or missing files are ignored; never blocks the CLI/TUI.
"""

import contextlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from .diagnostics.paths import resolve_app_state_paths

_MEMORY_FILENAME = "active-project.json"
_MEMORY_VERSION = 1
RECENT_WORDLIST_MAX = 5

# Test override (set via monkeypatch); production always uses resolve_app_state_paths().
_state_root_override: Path | None = None


@dataclass(frozen=True)
class ProjectMemory:
    active: Path | None
    recent: tuple[Path, ...]


def _memory_path() -> Path:
    paths = resolve_app_state_paths(state_root=_state_root_override)
    return paths.state_directory / _MEMORY_FILENAME


def _coerce_path(value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return Path(value).expanduser()
    except TypeError, ValueError:
        return None


def load_project_memory() -> ProjectMemory:
    path = _memory_path()
    if not path.is_file():
        return ProjectMemory(active=None, recent=())
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError, UnicodeError, json.JSONDecodeError:
        return ProjectMemory(active=None, recent=())
    if not isinstance(raw, dict):
        return ProjectMemory(active=None, recent=())
    active = _coerce_path(raw.get("active"))
    recent_raw = raw.get("recent")
    recent: list[Path] = []
    if isinstance(recent_raw, list):
        for item in recent_raw:
            candidate = _coerce_path(item)
            if candidate is None:
                continue
            if active is not None and candidate == active:
                continue
            if candidate not in recent:
                recent.append(candidate)
    return ProjectMemory(active=active, recent=tuple(recent))


def remembered_wordlist() -> Path | None:
    """Active pointer when the file still exists."""
    memory = load_project_memory()
    if memory.active is not None and memory.active.is_file():
        return memory.active.resolve()
    for path in memory.recent:
        if path.is_file():
            return path.resolve()
    return None


def list_recent_wordlists(*, max_items: int = RECENT_WORDLIST_MAX) -> tuple[Path, ...]:
    """Existing wordlist paths: active first, then recent (deduped)."""
    memory = load_project_memory()
    out: list[Path] = []
    for path in ((memory.active,) if memory.active is not None else ()) + memory.recent:
        try:
            resolved = path.expanduser()
            if not resolved.is_file():
                continue
            resolved = resolved.resolve()
        except OSError:
            continue
        if resolved in out:
            continue
        out.append(resolved)
        if len(out) >= max_items:
            break
    return tuple(out)


def remember_wordlist(wordlist: Path) -> None:
    """Set active pointer and prepend to recent. Best-effort; never raises."""
    try:
        resolved = wordlist.expanduser().resolve()
    except OSError:
        return
    if not resolved.is_file():
        return
    memory = load_project_memory()
    recent = [resolved]
    for path in ((memory.active,) if memory.active is not None else ()) + memory.recent:
        try:
            candidate = path.expanduser().resolve()
        except OSError:
            continue
        if candidate == resolved or candidate in recent:
            continue
        recent.append(candidate)
        if len(recent) >= RECENT_WORDLIST_MAX:
            break
    payload = {
        "version": _MEMORY_VERSION,
        "active": str(resolved),
        "recent": [str(path) for path in recent],
    }
    path = _memory_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        fd, tmp_name = _temp_in_dir(path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        except OSError:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
    except OSError:
        return


def _temp_in_dir(directory: Path) -> tuple[int, str]:
    import tempfile

    return tempfile.mkstemp(prefix=".active-project.", suffix=".tmp", dir=str(directory))
