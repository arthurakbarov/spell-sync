#!/usr/bin/env python3
"""Tests for scripts/check-ci-evidence.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location(
        "scripts.check_ci_evidence",
        ROOT / "scripts" / "check-ci-evidence.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def evidence_mod():
    return _load_module()


def _git_head(root: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
    ).strip()


def _write_success_summary(
    path: Path,
    *,
    head: str,
    digest: str,
    ci_input_digest: str = "",
    repo: Path | None = None,
    history: dict[str, int] | None = None,
) -> None:
    history = history or {"fullCiAttempts": 1, "fullCiFailures": 0, "fullCiSuccesses": 1}
    run_id = path.stem.removeprefix("ci-summary-") or "test-run"
    payload = {
        "schemaVersion": 4,
        "runId": run_id,
        "result": "success",
        "exitCode": 0,
        "mode": "full",
        "finalEvidence": True,
        "gitHeadAtRun": head,
        "gitHead": head,
        "gitBranch": "main",
        "gitDetached": False,
        "repositoryTreeDigest": digest,
        "treeDigest": digest,
        "treeDigestBefore": digest,
        "treeDigestAfter": digest,
        "treeStable": True,
        "ciInputDigest": ci_input_digest or digest,
        "ciImpactSchemaVersion": 1,
        "evidenceScope": "full-ci-inputs",
        "reusableAcrossNonCiCommits": True,
        "historyAtCompletion": history,
        "fullCiAttempts": history["fullCiAttempts"],
        "fullCiFailures": history["fullCiFailures"],
        "fullCiSuccesses": history["fullCiSuccesses"],
        "checks": [{"id": "tests.pytest", "status": "passed", "exitCode": 0}],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    if repo is not None:
        artifacts = repo / ".artifacts" / "ci"
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / f"ci-summary-{run_id}.json").write_text(json.dumps(payload), encoding="utf-8")
        (artifacts / f"ci-run-{run_id}.log").write_text("ok\n", encoding="utf-8")


def _install_registry(repo: Path) -> None:
    (repo / "ci").mkdir(parents=True, exist_ok=True)
    source = ROOT / "ci" / "ci-impact.toml"
    (repo / "ci" / "ci-impact.toml").write_text(
        source.read_text(encoding="utf-8"), encoding="utf-8"
    )


def test_stale_head_rejected(evidence_mod, tmp_path: Path) -> None:
    import subprocess

    from scripts.test_selection.tree_state import content_tree_digest

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-b", "main"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )
    (repo / "tracked.txt").write_text("clean\n", encoding="utf-8")
    _install_registry(repo)
    subprocess.run(
        ["git", "-C", str(repo), "add", "tracked.txt", "ci/ci-impact.toml"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True
    )
    digest = content_tree_digest(repo)
    from scripts.ci_impact.registry import load_registry
    from scripts.ci_input_state import compute_ci_input_state

    ci_input_digest = compute_ci_input_state(
        repo, load_registry(repo / "ci" / "ci-impact.toml")
    ).digest
    summary = tmp_path / "ci" / "ci-summary-stale-head-test.json"
    _write_success_summary(
        summary,
        head="0" * 40,
        digest=digest,
        ci_input_digest=ci_input_digest,
        repo=repo,
    )
    code, payload = evidence_mod.verify_ci_evidence(
        repo,
        summary,
        format_json=True,
    )
    assert code == 1
    assert payload.get("failedId") == "ci-evidence.run-head-unavailable"


def test_first_success_history_counts(tmp_path: Path) -> None:
    from scripts.ci_history import summarize_ci_history

    artifacts = tmp_path / "ci"
    artifacts.mkdir()
    _write_success_summary(
        artifacts / "ci-summary-one.json",
        head="abc",
        digest="def",
        history={"fullCiAttempts": 1, "fullCiFailures": 0, "fullCiSuccesses": 1},
    )
    counts = summarize_ci_history(artifacts)
    assert counts.full_ci_attempts == 1
    assert counts.full_ci_failures == 0
    assert counts.full_ci_successes == 1


def test_forged_success_summary_rejected_on_dirty_tree(evidence_mod, tmp_path: Path) -> None:
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-b", "main"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )
    (repo / "tracked.txt").write_text("clean\n", encoding="utf-8")
    (repo / "docs").mkdir()
    (repo / "docs" / "note.md").write_text("clean\n", encoding="utf-8")
    _install_registry(repo)
    subprocess.run(
        ["git", "-C", str(repo), "add", "tracked.txt", "docs/note.md", "ci/ci-impact.toml"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True
    )
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    from scripts.test_selection.tree_state import content_tree_digest

    digest = content_tree_digest(repo)
    from scripts.ci_impact.registry import load_registry
    from scripts.ci_input_state import compute_ci_input_state

    ci_input_digest = compute_ci_input_state(
        repo, load_registry(repo / "ci" / "ci-impact.toml")
    ).digest
    summary = tmp_path / "ci-summary.json"
    _write_success_summary(
        summary,
        head=head,
        digest=digest,
        ci_input_digest=ci_input_digest,
        repo=repo,
    )
    (repo / "docs" / "note.md").write_text("dirty\n", encoding="utf-8")
    code, payload = evidence_mod.verify_ci_evidence(repo, summary, format_json=True)
    assert code == 1
    assert payload.get("failedId") == "ci-evidence.dirty-tree"
