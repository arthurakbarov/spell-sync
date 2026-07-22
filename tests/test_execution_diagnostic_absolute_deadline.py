"""Absolute diagnostic deadline enforcement tests."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from scripts.execution_control.diagnostics import (
    DiagnosticBundleResult,
    _run_collector_process,
    collect_timeout_bundle,
)
from scripts.execution_control.models import ExecutionPlan
from scripts.execution_control.process_tree import ProcessResult

SCHEDULING_TOLERANCE = 0.08


def _plan(**overrides) -> ExecutionPlan:
    defaults = dict(
        run_id="diag-run",
        execution_id="ci:pytest",
        profile_id="ci-pytest",
        normalized_signature="sig",
        workload_fingerprint="wf",
        policy_fingerprint="pf",
        expected_seconds=60.0,
        soft_seconds=120.0,
        stall_seconds=None,
        hard_seconds=300.0,
        diagnostic_hard_seconds=0.05,
        termination_grace_seconds=5.0,
        progress_contract_id=None,
        termination_policy_id="owned-process-group",
        prediction_source="registry-default",
        confidence="none",
        sample_count=0,
        admission_decision="run",
        context_signature="macos|3.11|full-ci|501+|cov1|tui0|pkg0|unknown",
    )
    defaults.update(overrides)
    return ExecutionPlan(**defaults)


def _result() -> ProcessResult:
    return ProcessResult(
        exit_code=124,
        duration_seconds=1.0,
        timed_out=True,
        timeout_kind="hard",
        stdout_tail="",
        stderr_tail="",
        progress_event_count=0,
        maximum_progress_gap=0.0,
        start_time_iso="2026-01-01T00:00:00Z",
        end_time_iso="2026-01-01T00:00:01Z",
    )


def test_slow_collector_returns_within_budget(isolated_state_dir):
    del isolated_state_dir
    failures: list[str] = []
    started = time.monotonic()
    _run_collector_process(
        name="slow-sleep",
        payload={"seconds": 0.25},
        budget_seconds=0.05,
        failures=failures,
    )
    elapsed = time.monotonic() - started
    assert elapsed <= 0.05 + SCHEDULING_TOLERANCE
    assert failures
    assert any("slow-sleep:timeout" in item for item in failures)


@pytest.mark.parametrize(
    ("name", "payload"),
    [
        ("slow-sleep", {"seconds": 0.25}),
        ("bundle-write", {"path": "/tmp/unused.json", "body": {}, "delaySeconds": 0.25}),
        ("slow-mkdir", {"path": "/tmp/unused-dir", "seconds": 0.25}),
        ("slow-ps", {"seconds": 0.25, "ownedRootPid": 1}),
    ],
)
def test_adversarial_collectors_do_not_survive(isolated_state_dir, name, payload):
    del isolated_state_dir
    failures: list[str] = []
    started = time.monotonic()
    _run_collector_process(
        name=name,
        payload=payload,
        budget_seconds=0.05,
        failures=failures,
    )
    elapsed = time.monotonic() - started
    assert elapsed <= 0.05 + SCHEDULING_TOLERANCE
    assert failures


def test_timeout_bundle_respects_absolute_deadline_without_sync_fallback(
    isolated_state_dir, monkeypatch
):
    del isolated_state_dir

    def _forbidden_write(*args, **kwargs):
        raise AssertionError("synchronous bundle write after deadline is forbidden")

    monkeypatch.setattr(Path, "write_text", _forbidden_write)

    started = time.monotonic()
    bundle = collect_timeout_bundle(
        plan=_plan(diagnostic_hard_seconds=0.05),
        result=_result(),
        active_child=None,
        timeout_kind="hard",
    )
    elapsed = time.monotonic() - started
    assert isinstance(bundle, DiagnosticBundleResult)
    assert elapsed <= 0.05 + SCHEDULING_TOLERANCE
    assert bundle.incomplete or bundle.collector_failures
    if bundle.path is not None:
        payload = json.loads(Path(bundle.path).read_text(encoding="utf-8"))
        assert payload.get("incomplete") is True or payload.get("collectorFailures")
