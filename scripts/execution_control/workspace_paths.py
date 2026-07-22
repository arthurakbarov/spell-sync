"""Workspace path resolution for snapshot and private integrations."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_spell_sync_dev_root(public_root: Path) -> Path | None:
    env_root = os.environ.get("SPELL_SYNC_DEV_ROOT", "").strip()
    if env_root:
        candidate = Path(env_root).expanduser().resolve()
        if (candidate / "scripts" / "create-code-snapshot.py").is_file():
            return candidate
        return None
    resolved = public_root.resolve()
    candidates = (
        resolved.parent.parent / "spell-sync-dev",
        resolved.parent / "spell-sync-dev",
    )
    for candidate in candidates:
        if (candidate / "scripts" / "create-code-snapshot.py").is_file():
            return candidate.resolve()
    return None
