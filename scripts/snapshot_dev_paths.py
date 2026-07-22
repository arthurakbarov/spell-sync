"""Resolve spell-sync-dev root for portable snapshot and policy tests."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def resolve_spell_sync_dev_root(project_root: Path | None = None) -> Path | None:
    root = project_root or ROOT
    env_root = os.environ.get("SPELL_SYNC_DEV_ROOT", "").strip()
    if env_root:
        candidate = Path(env_root).expanduser().resolve()
        if (candidate / "scripts" / "create-code-snapshot.py").is_file():
            return candidate
    candidates = (
        root.parent.parent / "spell-sync-dev",
        root.parent / "spell-sync-dev",
    )
    for candidate in candidates:
        if (candidate / "scripts" / "create-code-snapshot.py").is_file():
            return candidate.resolve()
    return None
