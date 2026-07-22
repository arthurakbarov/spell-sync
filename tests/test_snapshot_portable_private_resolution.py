"""Portable discovery of spell-sync-dev under arbitrary extracted layout."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.snapshot_dev_paths import resolve_spell_sync_dev_root  # noqa: E402


def test_resolve_spell_sync_dev_from_sibling_layout(tmp_path: Path) -> None:
    actual = resolve_spell_sync_dev_root(ROOT)
    if actual is None:
        pytest.skip("spell-sync-dev not available in workspace")

    extracted = tmp_path / "extracted" / "code"
    tool = extracted / "spell-words" / "spell-sync"
    dev = extracted / "spell-sync-dev"
    tool.mkdir(parents=True)
    dev.mkdir(parents=True)
    (dev / "scripts").mkdir()
    (dev / "scripts" / "create-code-snapshot.py").write_text("# stub\n", encoding="utf-8")

    resolved = resolve_spell_sync_dev_root(tool)
    assert resolved == dev.resolve()


def test_resolve_returns_none_when_private_repo_missing(tmp_path: Path) -> None:
    lone = tmp_path / "spell-sync"
    lone.mkdir()
    assert resolve_spell_sync_dev_root(lone) is None
