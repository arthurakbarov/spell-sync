"""State directory paths for execution control (outside repository)."""

from __future__ import annotations

import os
from pathlib import Path

CONTROLLER_SCHEMA_VERSION = 1
HISTORY_SCHEMA_VERSION = 1


def state_root() -> Path:
    xdg = os.environ.get("XDG_STATE_HOME")
    if xdg:
        root = Path(xdg) / "spell-sync" / "execution-control"
    else:
        root = Path.home() / ".local" / "state" / "spell-sync" / "execution-control"
    root.mkdir(parents=True, exist_ok=True)
    return root


def history_database_path() -> Path:
    return state_root() / "history.sqlite3"


def timeout_bundle_dir(run_id: str) -> Path:
    path = state_root() / "timeouts" / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def plan_artifact_path(run_id: str) -> Path:
    return state_root() / "plans" / f"{run_id}.json"
