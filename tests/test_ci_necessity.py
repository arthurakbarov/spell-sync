#!/usr/bin/env python3
"""Tests for CI necessity planning."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_necessity_mod():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "scripts.check_ci_necessity",
        ROOT / "scripts" / "check-ci-necessity.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def necessity_mod():
    return _load_necessity_mod()


def assess_ci_necessity(*args, **kwargs):
    return _load_necessity_mod().assess_ci_necessity(*args, **kwargs)


def test_markdown_only_diff_is_lightweight_sufficient(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git(repo)
    (repo / "ci").mkdir()
    (repo / "ci" / "ci-impact.toml").write_text(
        (ROOT / "ci" / "ci-impact.toml").read_text(), encoding="utf-8"
    )
    (repo / "spell_sync").mkdir()
    (repo / "spell_sync" / "sample.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "docs").mkdir()
    (repo / "docs" / "note.md").write_text("hello\n", encoding="utf-8")
    _git_add_all(repo)
    _git_commit(repo, "base")
    base_head = _git_head(repo)
    (repo / "docs" / "note.md").write_text("hello world\n", encoding="utf-8")
    _git_add_all(repo)
    _git_commit(repo, "docs only")
    digest = _compute_ci_input_digest(repo)
    _write_summary(repo, head=base_head, ci_input_digest=digest)
    result = assess_ci_necessity(repo, base=base_head)
    assert result.result == "lightweight-sufficient"
    assert result.reason == "non-ci-inputs-only"


def test_product_change_requires_full_ci(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git(repo)
    (repo / "ci").mkdir()
    (repo / "ci" / "ci-impact.toml").write_text(
        (ROOT / "ci" / "ci-impact.toml").read_text(), encoding="utf-8"
    )
    (repo / "spell_sync").mkdir()
    (repo / "spell_sync" / "sample.py").write_text("x = 1\n", encoding="utf-8")
    _git_add_all(repo)
    _git_commit(repo, "base")
    base_head = _git_head(repo)
    (repo / "spell_sync" / "sample.py").write_text("x = 2\n", encoding="utf-8")
    _git_add_all(repo)
    _git_commit(repo, "product")
    digest = _compute_ci_input_digest(repo)
    _write_summary(repo, head=base_head, ci_input_digest=digest)
    result = assess_ci_necessity(repo, base=base_head)
    assert result.result == "full-required"


@pytest.mark.parametrize(
    ("rel_path", "content", "message"),
    [
        ("tests/test_sample.py", "def test_x():\n    assert True\n", "test"),
        ("pyproject.toml", '[project]\nname="x"\nversion="0.0.1"\n', "build"),
        ("scripts/ci_runner.py", "# ci\n", "toolchain"),
        ("spell_sync/data.txt", "payload\n", "package data"),
        ("mystery.dat", "unknown\n", "unknown"),
    ],
)
def test_ci_relevant_changes_require_full_ci(
    tmp_path: Path,
    rel_path: str,
    content: str,
    message: str,
) -> None:
    repo = _bootstrap_repo(tmp_path)
    base_head = _git_head(repo)
    target = repo / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git_add_all(repo)
    _git_commit(repo, message)
    digest = _compute_ci_input_digest(repo)
    _write_summary(repo, head=base_head, ci_input_digest=digest)
    result = assess_ci_necessity(repo, base=base_head)
    assert result.result == "full-required"


def test_agent_workflow_change_is_lightweight_sufficient(tmp_path: Path) -> None:
    repo = _bootstrap_repo(tmp_path)
    base_head = _git_head(repo)
    (repo / ".cursor" / "rules").mkdir(parents=True)
    (repo / ".cursor" / "rules" / "note.mdc").write_text("---\n", encoding="utf-8")
    _git_add_all(repo)
    _git_commit(repo, "agent rule")
    digest = _compute_ci_input_digest(repo)
    _write_summary(repo, head=base_head, ci_input_digest=digest)
    result = assess_ci_necessity(repo, base=base_head)
    assert result.result == "lightweight-sufficient"


def test_mixed_docs_and_product_requires_full_ci(tmp_path: Path) -> None:
    repo = _bootstrap_repo(tmp_path)
    base_head = _git_head(repo)
    digest = _compute_ci_input_digest(repo)
    _write_summary(repo, head=base_head, ci_input_digest=digest)
    (repo / "docs" / "note.md").write_text("updated\n", encoding="utf-8")
    (repo / "spell_sync" / "sample.py").write_text("x = 9\n", encoding="utf-8")
    _git_add_all(repo)
    _git_commit(repo, "mixed")
    result = assess_ci_necessity(repo, base=base_head)
    assert result.result == "full-required"


def test_untracked_production_file_requires_full_ci(tmp_path: Path) -> None:
    repo = _bootstrap_repo(tmp_path)
    base_head = _git_head(repo)
    digest = _compute_ci_input_digest(repo)
    _write_summary(repo, head=base_head, ci_input_digest=digest)
    (repo / "spell_sync" / "new.py").write_text("y = 1\n", encoding="utf-8")
    result = assess_ci_necessity(repo, base=base_head)
    assert result.result == "full-required"
    assert result.reason == "ci-input-dirty"


def test_untracked_markdown_is_lightweight_when_evidence_matches(tmp_path: Path) -> None:
    repo = _bootstrap_repo(tmp_path)
    base_head = _git_head(repo)
    digest = _compute_ci_input_digest(repo)
    _write_summary(repo, head=base_head, ci_input_digest=digest)
    (repo / "docs" / "draft.md").write_text("wip\n", encoding="utf-8")
    result = assess_ci_necessity(repo, base=base_head)
    assert result.result == "lightweight-sufficient"


def test_impact_registry_change_requires_full_ci(tmp_path: Path) -> None:
    repo = _bootstrap_repo(tmp_path)
    base_head = _git_head(repo)
    digest = _compute_ci_input_digest(repo)
    _write_summary(repo, head=base_head, ci_input_digest=digest)
    registry_path = repo / "ci" / "ci-impact.toml"
    registry_path.write_text(registry_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    _git_add_all(repo)
    _git_commit(repo, "registry")
    result = assess_ci_necessity(repo, base=base_head)
    assert result.result == "full-required"


def _bootstrap_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git(repo)
    (repo / "ci").mkdir()
    (repo / "ci" / "ci-impact.toml").write_text(
        (ROOT / "ci" / "ci-impact.toml").read_text(),
        encoding="utf-8",
    )
    (repo / "spell_sync").mkdir()
    (repo / "spell_sync" / "sample.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "docs").mkdir()
    (repo / "docs" / "note.md").write_text("hello\n", encoding="utf-8")
    _git_add_all(repo)
    _git_commit(repo, "base")
    return repo


def _init_git(repo: Path) -> None:
    subprocess.run(["git", "-C", str(repo), "init", "-b", "main"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "t@example.invalid"], check=True
    )
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)


def _git_add_all(repo: Path) -> None:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)


def _git_commit(repo: Path, message: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", message], check=True, capture_output=True
    )


def _git_head(repo: Path) -> str:
    return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()


def _compute_ci_input_digest(repo: Path) -> str:
    from scripts.ci_impact.registry import load_registry
    from scripts.ci_input_state import compute_ci_input_state

    return compute_ci_input_state(repo, load_registry(repo / "ci" / "ci-impact.toml")).digest


def _write_summary(repo: Path, *, head: str, ci_input_digest: str) -> None:
    artifacts = repo / ".artifacts" / "ci"
    artifacts.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": 4,
        "runId": "test-run",
        "result": "success",
        "exitCode": 0,
        "mode": "full",
        "finalEvidence": True,
        "gitHeadAtRun": head,
        "gitHead": head,
        "gitBranch": "main",
        "gitDetached": False,
        "repositoryTreeDigest": "tree",
        "treeDigest": "tree",
        "treeDigestBefore": "tree",
        "treeDigestAfter": "tree",
        "treeStable": True,
        "ciInputDigest": ci_input_digest,
        "ciImpactSchemaVersion": 1,
        "evidenceScope": "full-ci-inputs",
        "reusableAcrossNonCiCommits": True,
        "historyAtCompletion": {"fullCiAttempts": 1, "fullCiFailures": 0, "fullCiSuccesses": 1},
        "fullCiAttempts": 1,
        "fullCiFailures": 0,
        "fullCiSuccesses": 1,
        "checks": [{"id": "tests.pytest", "status": "passed", "exitCode": 0}],
    }
    (artifacts / "ci-summary.json").write_text(json.dumps(payload), encoding="utf-8")
    (artifacts / "ci-summary-test-run.json").write_text(json.dumps(payload), encoding="utf-8")
