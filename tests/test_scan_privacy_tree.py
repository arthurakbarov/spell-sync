"""Tests for lean privacy tree scan."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.scan_privacy_tree import scan_privacy_tree  # noqa: E402


def test_repository_privacy_scan_is_clean() -> None:
    hits = scan_privacy_tree(ROOT)
    assert hits == []


def test_scan_privacy_tree_script_succeeds() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "scan_privacy_tree.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PRIVACY_SCAN_RESULT=success" in proc.stdout


def test_scan_detects_github_pat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "leak.txt").write_text("token ghp_" + ("a" * 30) + "\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=ci@test", "-c", "user.name=ci", "add", "-A"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "-c", "user.email=ci@test", "-c", "user.name=ci", "commit", "-qm", "leak"],
        cwd=repo,
        check=True,
    )
    hits = scan_privacy_tree(repo)
    assert any(hit.category == "github-pat" for hit in hits)


def test_example_line_is_allowed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "docs.md").write_text(
        "example token: ghp_" + ("b" * 30) + "\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=ci@test", "-c", "user.name=ci", "add", "-A"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "-c", "user.email=ci@test", "-c", "user.name=ci", "commit", "-qm", "ex"],
        cwd=repo,
        check=True,
    )
    assert scan_privacy_tree(repo) == []
