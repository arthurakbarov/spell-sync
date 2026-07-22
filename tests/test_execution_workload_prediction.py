"""Focused pytest bootstrap workload cost before history exists."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.context import build_context  # noqa: E402
from scripts.execution_control.gate_admission import assess_gate_admission  # noqa: E402
from scripts.execution_control.gate_flow import preview_focused_child_plans  # noqa: E402
from scripts.execution_control.models import AdmissionDecision  # noqa: E402
from scripts.execution_control.prediction import predict_thresholds  # noqa: E402
from scripts.execution_control.registry import profile_for_execution_id  # noqa: E402
from tests.conftest_execution import echo_command  # noqa: E402


def _pytest_expected(registry, history_store, *, test_file_count: int) -> float:
    profile = profile_for_execution_id(registry, "focused:pytest")
    context = build_context(execution_mode="cluster", test_file_count=test_file_count)
    return predict_thresholds(
        profile=profile,
        registry=registry,
        history=history_store,
        execution_id="focused:pytest",
        workload_fingerprint_value=f"workload-{test_file_count}",
        context=context,
    ).expected_seconds


def test_cold_history_workload_prediction_scales(registry, history_store):
    counts = (0, 1, 20, 500, 1200)
    expected_values = [
        _pytest_expected(registry, history_store, test_file_count=count) for count in counts
    ]
    assert expected_values[-1] > expected_values[1]
    assert expected_values[-1] > 60
    assert expected_values[-2] > 60
    assert expected_values[-1] > expected_values[-2]


def test_normal_budget_large_focused_plan_narrows_without_subprocess(registry, history_store):
    profile = profile_for_execution_id(registry, "gate:focused-cluster")
    targets = [f"tests/workload_{index:04d}.py" for index in range(1200)]
    steps = (
        ("pytest", [sys.executable, "-m", "pytest", *targets]),
        ("validator", echo_command("validate")),
    )
    child_plans = preview_focused_child_plans(
        ROOT,
        registry,
        steps=steps,
        mode="cluster",
        test_file_count=len(targets),
    )
    admission, parent_plan = assess_gate_admission(
        ROOT,
        execution_id="gate:focused-cluster",
        profile=profile,
        registry=registry,
        history=history_store,
        child_plans=child_plans,
        command=[sys.executable, "scripts/run_focused_tests.py"],
        mode="cluster",
        required=False,
        test_file_count=len(targets),
    )
    assert admission.decision == AdmissionDecision.NARROW
    assert admission.reason == "edit-loop-budget-exceeded"
    assert parent_plan is not None


def test_normal_budget_small_focused_plan_runs(registry, history_store):
    profile = profile_for_execution_id(registry, "gate:focused-cluster")
    steps = (("pytest", [sys.executable, "-m", "pytest", "tests/test_core.py"]),)
    child_plans = preview_focused_child_plans(
        ROOT,
        registry,
        steps=steps,
        mode="cluster",
        test_file_count=1,
    )
    admission, parent_plan = assess_gate_admission(
        ROOT,
        execution_id="gate:focused-cluster",
        profile=profile,
        registry=registry,
        history=history_store,
        child_plans=child_plans,
        command=[sys.executable, "scripts/run_focused_tests.py"],
        mode="cluster",
        required=False,
        test_file_count=1,
    )
    assert admission.decision == AdmissionDecision.RUN
    assert parent_plan is not None
