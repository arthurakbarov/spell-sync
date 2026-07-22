"""Execution controller learning policy and overhead tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.controller import ExecutionController  # noqa: E402
from scripts.execution_control.history import HistoryStore  # noqa: E402
from scripts.execution_control.models import ExecutionPlan, ExecutionStatus  # noqa: E402
from scripts.execution_control.process_tree import ProcessResult  # noqa: E402
from tests.conftest_execution import sleep_command  # noqa: E402


def _fake_necessity(result: str = "full-required"):
    return SimpleNamespace(
        assess_ci_necessity=lambda _root: SimpleNamespace(
            result=result,
            reusable_run_head="",
        )
    )


def _sample_plan(**overrides) -> ExecutionPlan:
    defaults = {
        "run_id": "controller-run-001",
        "execution_id": "focused:pytest",
        "profile_id": "ci-child",
        "normalized_signature": "controller-signature" * 2,
        "workload_fingerprint": "workload" * 8,
        "policy_fingerprint": "policy" * 8,
        "expected_seconds": 45.0,
        "soft_seconds": 0.05,
        "stall_seconds": None,
        "hard_seconds": 2.0,
        "diagnostic_hard_seconds": 10.0,
        "termination_grace_seconds": 0.3,
        "progress_contract_id": None,
        "termination_policy_id": "owned-process-group",
        "prediction_source": "registry-default",
        "confidence": "none",
        "sample_count": 0,
        "admission_decision": "run",
        "context_signature": "macos|3.11|cluster|1|cov0|tui0|pkg0|unknown",
    }
    defaults.update(overrides)
    return ExecutionPlan(**defaults)


@pytest.fixture
def controller(registry, history):
    return ExecutionController(
        root=ROOT,
        registry=registry,
        history=history,
        enforce_hard=True,
        enforce_stall=False,
    )


def test_classify_success_accepted_for_learning(controller):
    plan = _sample_plan()
    result = ProcessResult(
        exit_code=0,
        duration_seconds=0.01,
        timed_out=False,
        timeout_kind=None,
        stdout_tail="",
        stderr_tail="",
        progress_event_count=0,
        maximum_progress_gap=0.0,
        start_time_iso="2026-01-01T00:00:00Z",
        end_time_iso="2026-01-01T00:00:01Z",
    )
    status, accepted, quarantine = controller._classify_result(plan, result)
    assert status == ExecutionStatus.SUCCESS
    assert accepted is True
    assert quarantine is None


def test_classify_success_slow_quarantined(controller):
    plan = _sample_plan(soft_seconds=0.01)
    result = ProcessResult(
        exit_code=0,
        duration_seconds=0.5,
        timed_out=False,
        timeout_kind=None,
        stdout_tail="",
        stderr_tail="",
        progress_event_count=0,
        maximum_progress_gap=0.0,
        start_time_iso="2026-01-01T00:00:00Z",
        end_time_iso="2026-01-01T00:00:01Z",
    )
    status, accepted, quarantine = controller._classify_result(plan, result)
    assert status == ExecutionStatus.SUCCESS_SLOW
    assert accepted is False
    assert quarantine == "soft-overrun"


def test_classify_timeout_not_learned(controller):
    plan = _sample_plan()
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
    status, accepted, quarantine = controller._classify_result(plan, result)
    assert status == ExecutionStatus.TIMEOUT_HARD
    assert accepted is False
    assert quarantine == "timeout-hard"


def test_success_learns(registry, history, isolated_state_dir):
    del isolated_state_dir
    controller = ExecutionController(
        root=ROOT,
        registry=registry,
        history=history,
        enforce_hard=True,
        enforce_stall=False,
    )
    with patch(
        "scripts.execution_control.admission._load_ci_necessity",
        return_value=_fake_necessity(),
    ):
        plan, state = controller.prepare_plan(
            execution_id="focused:pytest",
            command=sleep_command(0.05),
            mode="cluster",
            required=True,
            test_file_count=1,
        )
    assert state == "run"
    assert plan is not None
    execution = controller.run(plan, sleep_command(0.05), cwd=ROOT)
    assert execution.exit_code == 0
    assert execution.timing["result"] == ExecutionStatus.SUCCESS.value
    rows = history.fetch_learning_durations(
        execution_id="focused:pytest",
        workload_fingerprint=plan.workload_fingerprint,
    )
    assert rows


def test_failure_does_not_learn(registry, history, isolated_state_dir):
    del isolated_state_dir
    controller = ExecutionController(
        root=ROOT,
        registry=registry,
        history=history,
        enforce_hard=True,
        enforce_stall=False,
    )
    failing = [sys.executable, "-c", "raise SystemExit(3)"]
    with patch(
        "scripts.execution_control.admission._load_ci_necessity",
        return_value=_fake_necessity(),
    ):
        plan, _ = controller.prepare_plan(
            execution_id="focused:pytest",
            command=failing,
            mode="cluster",
            required=True,
            test_file_count=1,
        )
    assert plan is not None
    execution = controller.run(plan, failing, cwd=ROOT)
    assert execution.exit_code == 3
    assert execution.timing["result"] == ExecutionStatus.FAILED.value
    assert (
        history.fetch_learning_durations(
            execution_id="focused:pytest",
            workload_fingerprint=plan.workload_fingerprint,
        )
        == []
    )


def test_prepare_plan_blocks_duplicate_active(controller):
    with patch(
        "scripts.execution_control.admission._load_ci_necessity",
        return_value=_fake_necessity(),
    ):
        first_plan, first_state = controller.prepare_plan(
            execution_id="gate:focused-module",
            command=["python3", "-m", "pytest"],
            mode="exact",
            required=True,
        )
        assert first_plan is not None
        assert first_state == "run"
        second_plan, second_state = controller.prepare_plan(
            execution_id="gate:focused-module",
            command=["python3", "-m", "pytest"],
            mode="exact",
            required=True,
        )
    assert second_plan is None
    assert second_state == ExecutionStatus.BLOCKED_DUPLICATE.value


def test_controller_overhead_differential_bounded(registry, history, isolated_state_dir):
    del isolated_state_dir
    import time as time_module

    direct_cmd = [sys.executable, "-c", "import time; time.sleep(1.0)"]
    direct_start = time_module.monotonic()
    subprocess.run(direct_cmd, cwd=ROOT, check=False)
    direct_duration = time_module.monotonic() - direct_start

    controller = ExecutionController(
        root=ROOT,
        registry=registry,
        history=HistoryStore.open(),
        enforce_hard=True,
        enforce_stall=False,
    )
    with patch(
        "scripts.execution_control.admission._load_ci_necessity",
        return_value=_fake_necessity(),
    ):
        plan, state = controller.prepare_plan(
            execution_id="focused:pytest",
            command=direct_cmd,
            mode="cluster",
            required=True,
            test_file_count=1,
        )
    assert plan is not None and state == "run"
    controlled_start = time_module.monotonic()
    controller.run(plan, direct_cmd, cwd=ROOT)
    controlled_duration = time_module.monotonic() - controlled_start
    overhead = controlled_duration - direct_duration
    tolerance = max(0.1, direct_duration * 0.02)
    assert overhead <= tolerance + 0.15
