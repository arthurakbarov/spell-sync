"""Pull and push preview screens surface safety copy."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_preview_screens_reference_safety_constants() -> None:
    pull = (ROOT / "spell_sync/tui/screens/pull_screen.py").read_text(encoding="utf-8")
    push = (ROOT / "spell_sync/tui/screens/preview_screen.py").read_text(encoding="utf-8")
    assert "PULL_PREVIEW_SAFETY" in pull
    assert "PUSH_PREVIEW_SAFETY" in push
