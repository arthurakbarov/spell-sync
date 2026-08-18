"""Pull and push preview screens surface safety copy."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_preview_screens_reference_safety_constants() -> None:
    pull = (ROOT / "spell_sync/tui/screens/pull_screen.py").read_text(encoding="utf-8")
    push_copy = (ROOT / "spell_sync/application/push_preview_copy.py").read_text(encoding="utf-8")
    assert "PULL_PREVIEW_SAFETY" in pull
    assert "PUSH_PREVIEW_SAFETY" in push_copy
