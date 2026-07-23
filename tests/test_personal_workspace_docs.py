"""Personal workspace documentation contract."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_personal_workspace_doc() -> None:
    text = (ROOT / "docs/PERSONAL_WORKSPACE.md").read_text(encoding="utf-8")
    assert "wordlist.txt" in text
    assert "spell-sync.toml" in text
    assert "optional" in text.lower()
    assert "Git" in text
