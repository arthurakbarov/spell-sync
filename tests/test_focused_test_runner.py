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
def runner_mod():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    return _load_module("run_focused_tests", ROOT / "scripts" / "run_focused_tests.py")


def test_exact_successful_run_skipped(ledger_mod, tmp_path: Path) -> None:
    ledger = ledger_mod.TestRunLedger(tmp_path)
    command = [sys.executable, "-m", "pytest", "tests/test_core.py", "-q"]
    targets = ["tests/test_core.py"]
    clusters = ["packaging"]
    run_key = ledger.compute_key(command=command, targets=targets, clusters=clusters)
    now = datetime.now(timezone.utc)
    ledger.record_success(
        run_key=run_key,
        command=command,
        targets=targets,
        clusters=clusters,
        started_at=now,
        completed_at=now,
        duration_seconds=1.0,
        validation_level=2,
        final_focused_evidence=True,
        steps=[],
    )
    found = ledger.find_success(
        run_key=run_key,
        command=command,
        targets=targets,
        clusters=clusters,
    )
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
                "command": ["python3", "-m", "pytest", "tests/test_core.py", "-q"],
                "result": "failed",
                "exitCode": 1,
                "startedAt": "2026-01-01T00:00:00+00:00",
                "completedAt": "2026-01-01T00:00:01+00:00",
                "durationSeconds": 1.0,
                "treeDigest": "deadbeef",
                "targets": ["tests/test_core.py"],
                "clusters": [],
                "validationLevel": 2,
                "finalFocusedEvidence": True,
                "steps": [],
            }
        },
        "order": ["abc"],
    }
    index_path.write_text(json.dumps(payload), encoding="utf-8")
    ledger = ledger_mod.TestRunLedger(tmp_path)
    found = ledger.find_success(
        run_key="abc",
        command=["python3", "-m", "pytest", "tests/test_core.py", "-q"],
        targets=["tests/test_core.py"],
        clusters=[],
    )
    assert found is None


def test_corrupt_ledger_ignored_safely(ledger_mod, tmp_path: Path) -> None:
    index_path = tmp_path / ".artifacts" / "test-runs" / "index.json"
    index_path.parent.mkdir(parents=True)
    index_path.write_text("{not-json", encoding="utf-8")
    ledger = ledger_mod.TestRunLedger(tmp_path)
    assert ledger.iter_records() == []


def test_command_argv_included_in_run_key(ledger_mod, tmp_path: Path) -> None:
    ledger = ledger_mod.TestRunLedger(tmp_path)
    key_a = ledger.compute_key(
        command=["python3", "-m", "pytest", "tests/a.py", "-q"],
        targets=["tests/a.py"],
        clusters=[],
    )
    key_b = ledger.compute_key(
        command=["python3", "-m", "pytest", "tests/b.py", "-q"],
        targets=["tests/b.py"],
        clusters=[],
    )
    assert key_a != key_b


def test_cluster_a_then_b_then_a_reuses_a(ledger_mod, tmp_path: Path) -> None:
    ledger = ledger_mod.TestRunLedger(tmp_path)
    command_a = [sys.executable, "-m", "pytest", "tests/test_pull_safety.py", "-q"]
    command_b = [sys.executable, "-m", "pytest", "tests/test_transaction_safety.py", "-q"]
    key_a = ledger.compute_key(
        command=command_a,
        targets=["tests/test_pull_safety.py"],
        clusters=["pull"],
    )
    key_b = ledger.compute_key(
        command=command_b,
        targets=["tests/test_transaction_safety.py"],
        clusters=["transaction"],
    )
    now = datetime.now(timezone.utc)
    ledger.record_success(
        run_key=key_a,
        command=command_a,
        targets=["tests/test_pull_safety.py"],
        clusters=["pull"],
        started_at=now,
        completed_at=now,
        duration_seconds=1.0,
        validation_level=2,
        final_focused_evidence=True,
        steps=[],
    )
    ledger.record_success(
        run_key=key_b,
        command=command_b,
        targets=["tests/test_transaction_safety.py"],
        clusters=["transaction"],
        started_at=now,
        completed_at=now,
        duration_seconds=2.0,
        validation_level=2,
        final_focused_evidence=True,
        steps=[],
    )
    found_a = ledger.find_success(
        run_key=key_a,
        command=command_a,
        targets=["tests/test_pull_safety.py"],
        clusters=["pull"],
    )
    assert found_a is not None


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
