"""First-run wizard does not start with Push."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_setup_preview_does_not_push() -> None:
    source = (ROOT / "spell_sync/tui/screens/setup_welcome_screen.py").read_text(encoding="utf-8")
    assert 'operation="push"' not in source
    assert "SetupWelcomeScreen" in source
    assert "WELCOME_INTRO" in source
