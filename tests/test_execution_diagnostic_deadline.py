"""Bounded diagnostic collector tests."""

from __future__ import annotations

import json
import time
from pathlib import Path

from scripts.execution_control.diagnostics import _run_collector_process, collect_timeout_bundle
from scripts.execution_control.models import ExecutionPlan
from scripts.execution_control.process_tree import ProcessResult


def _plan(**overrides) -> ExecutionPlan:
    defaults = dict(
        run_id="diag-run",
        execution_id="ci:pytest",
        profile_id="ci-child",
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
    assert elapsed <= 0.15
    assert failures
    assert any("slow-sleep:timeout" in item for item in failures)


def test_timeout_bundle_respects_diagnostic_deadline(isolated_state_dir):
    del isolated_state_dir
    result = ProcessResult(
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
    started = time.monotonic()
    bundle = collect_timeout_bundle(
        plan=_plan(diagnostic_hard_seconds=0.05),
        result=result,
        active_child=None,
        timeout_kind="hard",
    )
    elapsed = time.monotonic() - started
    assert elapsed <= 0.2
    if bundle.path is not None:
        payload = json.loads(Path(bundle.path).read_text(encoding="utf-8"))
        assert payload["collectorFailures"]
