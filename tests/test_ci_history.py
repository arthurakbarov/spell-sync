#!/usr/bin/env python3
"""Tests for CI history aggregation."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_ci_history():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location(
        "scripts.ci_history",
        ROOT / "scripts" / "ci_history.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_summary(
    artifacts: Path, name: str, *, result: str, exit_code: int, mode: str = "full"
) -> None:
    payload = {
        "schemaVersion": 3,
        "runId": name,
        "result": result,
        "exitCode": exit_code,
        "mode": mode,
        "finalEvidence": mode == "full" and result == "success",
    }
    (artifacts / f"ci-summary-{name}.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture()
def ci_history_mod():
    return _load_ci_history()


def test_first_successful_run_counts(ci_history_mod, tmp_path: Path) -> None:
    artifacts = tmp_path / "ci"
    artifacts.mkdir()
    _write_summary(artifacts, "one", result="success", exit_code=0)
    counts = ci_history_mod.summarize_ci_history(artifacts)
    assert counts.full_ci_attempts == 1
    assert counts.full_ci_failures == 0
    assert counts.full_ci_successes == 1


def test_first_failed_run_counts(ci_history_mod, tmp_path: Path) -> None:
    artifacts = tmp_path / "ci"
    artifacts.mkdir()
    _write_summary(artifacts, "one", result="failed", exit_code=1)
    counts = ci_history_mod.summarize_ci_history(artifacts)
    assert counts.full_ci_attempts == 1
    assert counts.full_ci_failures == 1
    assert counts.full_ci_successes == 0


def test_four_failures_one_success(ci_history_mod, tmp_path: Path) -> None:
    artifacts = tmp_path / "ci"
    artifacts.mkdir()
    for idx in range(4):
        _write_summary(artifacts, f"f{idx}", result="failed", exit_code=1)
    _write_summary(artifacts, "ok", result="success", exit_code=0)
    counts = ci_history_mod.summarize_ci_history(artifacts)
    assert counts.full_ci_attempts == 5
    assert counts.full_ci_failures == 4
    assert counts.full_ci_successes == 1


def test_diagnostic_runs_excluded(ci_history_mod, tmp_path: Path) -> None:
    artifacts = tmp_path / "ci"
    artifacts.mkdir()
    _write_summary(artifacts, "diag", result="success", exit_code=0, mode="only")
    counts = ci_history_mod.summarize_ci_history(artifacts)
    assert counts.full_ci_attempts == 0
