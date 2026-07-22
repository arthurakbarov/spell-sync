"""Diagnostic collector timeout must not trigger synchronous ps fallback."""

from __future__ import annotations

import time

from scripts.execution_control.diagnostics import collect_timeout_bundle
from scripts.execution_control.models import ExecutionPlan
from scripts.execution_control.process_tree import ProcessResult

SCHEDULING_TOLERANCE = 0.08


def _plan(**overrides) -> ExecutionPlan:
    defaults = dict(
        run_id="diag-no-fallback",
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
        context_signature="test",
    )
    defaults.update(overrides)
    return ExecutionPlan(**defaults)


def _result(*, owned_root_pid: int | None = 4242) -> ProcessResult:
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
        owned_root_pid=owned_root_pid,
        owned_pgid=owned_root_pid,
    )


def test_non_null_pid_scan_bounded_without_sync_fallback(isolated_state_dir, monkeypatch):
    del isolated_state_dir

    def _slow_collect_descendants(_pid: int) -> set[int]:
        time.sleep(0.25)
        return {1, 2, 3}

    monkeypatch.setattr(
        "scripts.execution_control.diagnostics.collect_descendants",
        _slow_collect_descendants,
    )

    started = time.monotonic()
    bundle = collect_timeout_bundle(
        plan=_plan(diagnostic_hard_seconds=0.05),
        result=_result(owned_root_pid=99999),
        active_child="ci:pytest",
        timeout_kind="hard",
    )
    elapsed = time.monotonic() - started
    assert elapsed <= 0.05 + SCHEDULING_TOLERANCE
    assert bundle.incomplete
    assert bundle.collector_failures


def test_sync_owned_snapshot_forbidden_after_collector_timeout(isolated_state_dir):
    del isolated_state_dir
    diagnostics = __import__(
        "scripts.execution_control.diagnostics",
        fromlist=["diagnostics"],
    )
    assert not hasattr(diagnostics, "_owned_process_snapshot")
