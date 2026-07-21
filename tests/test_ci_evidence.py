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
    history: dict[str, int] | None = None,
) -> None:
    history = history or {"fullCiAttempts": 1, "fullCiFailures": 0, "fullCiSuccesses": 1}
    payload = {
        "schemaVersion": 3,
        "runId": path.stem.removeprefix("ci-summary-"),
        "result": "success",
        "exitCode": 0,
        "mode": "full",
        "finalEvidence": True,
        "gitHead": head,
        "gitBranch": "main",
        "gitDetached": False,
        "treeDigest": digest,
        "treeDigestBefore": digest,
        "treeDigestAfter": digest,
        "treeStable": True,
        "historyAtCompletion": history,
        "fullCiAttempts": history["fullCiAttempts"],
        "fullCiFailures": history["fullCiFailures"],
        "fullCiSuccesses": history["fullCiSuccesses"],
        "checks": [{"id": "tests.pytest", "status": "passed", "exitCode": 0}],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_stale_head_rejected(evidence_mod, tmp_path: Path) -> None:
    from scripts.test_selection.tree_state import content_tree_digest

    digest = content_tree_digest(ROOT)
    summary = tmp_path / "ci" / "ci-summary-stale-head-test.json"
    _write_success_summary(summary, head="0" * 40, digest=digest)
    code, payload = evidence_mod.verify_ci_evidence(
        ROOT,
        summary,
        format_json=True,
    )
    assert code == 1
    assert payload.get("failedId") == "ci-evidence.head-mismatch"


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
