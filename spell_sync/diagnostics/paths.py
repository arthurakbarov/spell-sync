"""Platform-specific application state paths."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ..paths import app_support_dir, home_dir, is_macos, is_windows


@dataclass(frozen=True)
class AppStatePaths:
    state_directory: Path
    history_file: Path
    history_lock: Path
    technical_log: Path


def _linux_state_home() -> Path:
    xdg = os.getenv("XDG_STATE_HOME")
    if xdg:
        return Path(xdg).expanduser().resolve()
    return (home_dir() / ".local" / "state").resolve()


def resolve_app_state_paths(*, state_root: Path | None = None) -> AppStatePaths:
    """Resolve absolute application state paths.

    When ``state_root`` is provided (tests), both history and technical log live
    under that directory.
    """
    if state_root is not None:
        root = state_root.expanduser().resolve()
        return AppStatePaths(
            state_directory=root,
            history_file=root / "operation-history.jsonl",
            history_lock=root / "operation-history.lock",
            technical_log=root / "spell-sync.log",
        )

    if is_macos():
        state_directory = (app_support_dir() / "spell-sync").resolve()
        technical_log = (
            home_dir() / "Library" / "Logs" / "spell-sync" / "spell-sync.log"
        ).resolve()
    elif is_windows():
        local = Path(os.getenv("LOCALAPPDATA") or home_dir()).expanduser().resolve()
        state_directory = (local / "spell-sync").resolve()
        technical_log = (state_directory / "logs" / "spell-sync.log").resolve()
    else:
        state_directory = (_linux_state_home() / "spell-sync").resolve()
        technical_log = (state_directory / "spell-sync.log").resolve()

    return AppStatePaths(
        state_directory=state_directory,
        history_file=state_directory / "operation-history.jsonl",
        history_lock=state_directory / "operation-history.lock",
        technical_log=technical_log,
    )
