"""Dashboard exposes three primary user actions."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_primary_buttons_present() -> None:
    source = (ROOT / "spell_sync/tui/screens/dashboard.py").read_text(encoding="utf-8")
    assert 'id="btn-status"' in source
    assert 'id="btn-pull"' in source
    assert 'id="btn-push"' in source
    assert "CHECK_APPS_LABEL" in source
    assert "COLLECT_WORDS_LABEL" in source
    assert "UPDATE_APPS_LABEL" in source
