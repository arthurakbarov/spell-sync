"""Workspace path resolution for snapshot and private integrations."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SnapshotWorkspaceLayout:
    root: Path
    spell_words: Path
    spell_sync: Path
    spell_sync_dev: Path


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


def resolve_snapshot_workspace_layout(
    workspace_root: Path | None,
) -> SnapshotWorkspaceLayout | None:
    if workspace_root is None:
        return None
    root = workspace_root.expanduser().resolve()
    spell_words = root / "spell-words"
    spell_sync_dev = root / "spell-sync-dev"
    spell_sync_nested = spell_words / "spell-sync"
    spell_sync_flat = root / "spell-sync"
    spell_sync = spell_sync_nested if spell_sync_nested.is_dir() else spell_sync_flat
    if not spell_words.is_dir() or not spell_sync.is_dir() or not spell_sync_dev.is_dir():
        return None
    snapshot_script = spell_sync_dev / "scripts" / "create-code-snapshot.py"
    if not snapshot_script.is_file():
        return None
    return SnapshotWorkspaceLayout(
        root=root,
        spell_words=spell_words,
        spell_sync=spell_sync,
        spell_sync_dev=spell_sync_dev,
    )


def validate_snapshot_workspace(workspace_root: Path | None) -> tuple[bool, str]:
    layout = resolve_snapshot_workspace_layout(workspace_root)
    if layout is None:
        return False, "snapshot.workspace-layout-invalid"
    return True, ""
