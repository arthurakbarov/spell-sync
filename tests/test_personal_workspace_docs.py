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
    assert "Dropbox" in text or "synced folder" in text.lower()
    assert "Change word list location" in text
    assert "PERSONAL_GIT_REMOTE.md" in text


def test_personal_git_remote_doc() -> None:
    text = (ROOT / "docs/PERSONAL_GIT_REMOTE.md").read_text(encoding="utf-8")
    assert "private" in text.lower()
    assert "gh repo create" in text
    assert "init-personal-github-remote.sh" in text
    script = ROOT / "docs/examples/init-personal-github-remote.sh"
    assert script.is_file()
    body = script.read_text(encoding="utf-8")
    assert "--private" in body
    assert "gh repo create" in body
