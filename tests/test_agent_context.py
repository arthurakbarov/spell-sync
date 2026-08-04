"""agent_context.py read-only rollup."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "agent_context.py"


def test_agent_context_json_shape() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--json", "--purpose", "local"],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["repository"] == "spell-sync"
    assert isinstance(payload["branch"], str) and payload["branch"]
    assert isinstance(payload["head"], str) and len(payload["head"]) >= 7
    assert isinstance(payload["dirty"], bool)
    assert payload["necessityResult"] in {
        "no-action",
        "commit-gate-sufficient",
        "lightweight-sufficient",
        "full-required",
    }
    assert "run_dev_loop" in str(payload["suggestedCheckpoint"])
    assert payload["rules"]
    assert payload["skills"]
    assert payload["docs"]
    assert isinstance(payload["workspaceRepos"], list)
    for item in payload["workspaceRepos"]:
        assert set(item) >= {
            "name",
            "displayPath",
            "branch",
            "head",
            "headShort",
            "dirty",
            "stagedCount",
            "unstagedCount",
            "untrackedCount",
        }
        assert item["displayPath"].startswith("$HOME/") or "/" not in item["displayPath"]


def test_agent_context_text_keys() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    assert "AGENT_CONTEXT_BRANCH=" in proc.stdout
    assert "AGENT_CONTEXT_NECESSITY=" in proc.stdout
    assert "AGENT_CONTEXT_SUGGESTED_CHECKPOINT=" in proc.stdout
    assert "AGENT_CONTEXT_WORKSPACE_REPO_COUNT=" in proc.stdout


def test_resolve_siblings_nested_layout(tmp_path: Path, monkeypatch) -> None:
    from scripts import agent_context as mod

    code = tmp_path / "code"
    words = code / "spell-words"
    tool = words / "spell-sync"
    dev = code / "spell-sync-dev"
    for path in (words, tool, dev):
        path.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init"], check=True, cwd=path, capture_output=True)

    monkeypatch.setattr(mod, "ROOT", tool)
    monkeypatch.delenv("SPELL_WORDS", raising=False)
    monkeypatch.delenv("SPELL_SYNC_DEV", raising=False)
    monkeypatch.delenv("SPELL_SYNC_WORKSPACE", raising=False)

    found = mod.resolve_sibling_roots()
    assert found["spell-words"] == words.resolve()
    assert found["spell-sync-dev"] == dev.resolve()
