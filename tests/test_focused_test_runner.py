#!/usr/bin/env python3
"""Tests for scripts/run_focused_tests.py and executed-test ledger."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def ledger_mod():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    return _load_module("test_selection_ledger", ROOT / "scripts" / "test_selection" / "ledger.py")


@pytest.fixture()
def steps_mod():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    return _load_module("plan_steps", ROOT / "scripts" / "test_selection" / "plan_steps.py")


@pytest.fixture()
def runner_mod():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    return _load_module("run_focused_tests", ROOT / "scripts" / "run_focused_tests.py")


def _sample_steps(steps_mod, *, target: str = "tests/test_core.py") -> tuple:
    PlannedStep = steps_mod.PlannedStep
    return (
        PlannedStep(
            kind="pytest",
            argv=(sys.executable, "-m", "pytest", target, "-q"),
        ),
    )


def _sample_metadata(*, cluster: str = "packaging") -> tuple[str, ...]:
    return (
        "schema=2",
        "level=2",
        f"clusters={cluster}",
        "required=",
    )


def test_exact_successful_run_skipped(ledger_mod, steps_mod, tmp_path: Path) -> None:
    ledger = ledger_mod.TestRunLedger(tmp_path)
    steps = _sample_steps(steps_mod)
    metadata = _sample_metadata()
    run_key = ledger.compute_key(steps=steps, metadata=metadata)
    now = datetime.now(timezone.utc)
    ledger.record_success(
        run_key=run_key,
        steps=steps,
        metadata=metadata,
        started_at=now,
        completed_at=now,
        duration_seconds=1.0,
        validation_level=2,
        final_focused_evidence=True,
        step_results=[
            ledger_mod.StepResult(
                kind=steps[0].kind,
                command=list(steps[0].argv),
                exit_code=0,
                duration_seconds=1.0,
            )
        ],
    )
    found = ledger.find_success(run_key=run_key, steps=steps, metadata=metadata)
    assert found is not None
    assert found.result == "success"


def test_failed_run_not_reused(ledger_mod, tmp_path: Path) -> None:
    index_path = tmp_path / ".artifacts" / "test-runs" / "index.json"
    index_path.parent.mkdir(parents=True)
    payload = {
        "schemaVersion": 2,
        "records": {
            "abc": {
                "schemaVersion": 2,
                "runKey": "abc",
                "metadata": ["schema=2"],
                "result": "failed",
                "exitCode": 1,
                "startedAt": "2026-01-01T00:00:00+00:00",
                "completedAt": "2026-01-01T00:00:01+00:00",
                "durationSeconds": 1.0,
                "treeDigest": "deadbeef",
                "steps": [],
            }
        },
        "order": ["abc"],
    }
    index_path.write_text(json.dumps(payload), encoding="utf-8")
    ledger = ledger_mod.TestRunLedger(tmp_path)
    found = ledger.find_success(
        run_key="abc",
        steps=(),
        metadata=("schema=2",),
    )
    assert found is None


def test_corrupt_ledger_ignored_safely(ledger_mod, tmp_path: Path) -> None:
    index_path = tmp_path / ".artifacts" / "test-runs" / "index.json"
    index_path.parent.mkdir(parents=True)
    index_path.write_text("{not-json", encoding="utf-8")
    ledger = ledger_mod.TestRunLedger(tmp_path)
    assert ledger.iter_records() == []


def test_same_pytest_different_static_targets_changes_run_key(
    ledger_mod, steps_mod, tmp_path: Path
) -> None:
    ledger = ledger_mod.TestRunLedger(tmp_path)
    PlannedStep = steps_mod.PlannedStep
    pytest_step = PlannedStep(
        kind="pytest",
        argv=(sys.executable, "-m", "pytest", "tests/test_core.py", "-q"),
    )
    key_a = ledger.compute_key(
        steps=(
            pytest_step,
            PlannedStep(
                kind="ruff-check", argv=(sys.executable, "-m", "ruff", "check", "spell_sync")
            ),
        ),
        metadata=_sample_metadata(),
    )
    key_b = ledger.compute_key(
        steps=(
            pytest_step,
            PlannedStep(kind="ruff-check", argv=(sys.executable, "-m", "ruff", "check", "scripts")),
        ),
        metadata=_sample_metadata(),
    )
    assert key_a != key_b


def test_force_reruns(runner_mod) -> None:
    with patch.object(runner_mod, "run_command", return_value=(0, 0.1)):
        with patch.object(runner_mod.TestRunLedger, "find_success", return_value=object()):
            rc = runner_mod.main(["--target", "tests/test_core.py", "--force"])
    assert rc == 0


def test_skipped_when_already_passed(runner_mod, capsys) -> None:
    record = type(
        "Record",
        (),
        {"duration_seconds": 2.5, "result": "success", "exit_code": 0},
    )()
    with patch.object(runner_mod.TestRunLedger, "find_success", return_value=record):
        with patch.object(runner_mod, "run_command") as run_command:
            rc = runner_mod.main(["--target", "tests/test_core.py"])
    run_command.assert_not_called()
    assert rc == 0
    output = capsys.readouterr().out
    assert "TEST_RUN_RESULT=skipped" in output
    assert "already-passed-for-current-state" in output


def test_docs_only_runs_validators(runner_mod, capsys) -> None:
    with patch.object(runner_mod, "collect_changed_files", return_value=["docs/ARCHITECTURE.md"]):
        with patch.object(runner_mod.TestRunLedger, "find_success", return_value=None):
            with patch.object(runner_mod, "run_command", return_value=(0, 0.1)):
                rc = runner_mod.main([])
    output = capsys.readouterr().out
    assert rc == 0
    assert "TEST_RUN_RESULT=success" in output
    assert "TEST_RUN_PYTEST=skipped" in output
    assert "TEST_RUN_VALIDATORS=" in output
