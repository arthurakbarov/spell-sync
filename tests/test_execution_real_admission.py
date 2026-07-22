"""Real admission after concrete child plan previews."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.gate_admission import assess_gate_admission  # noqa: E402
from scripts.execution_control.gate_flow import preview_focused_child_plans  # noqa: E402
from scripts.execution_control.models import AdmissionDecision  # noqa: E402
from scripts.execution_control.registry import profile_for_execution_id  # noqa: E402
from tests.conftest_execution import echo_command  # noqa: E402


def _fake_necessity(result: str = "full-required"):
    from types import SimpleNamespace

    return SimpleNamespace(
        assess_ci_necessity=lambda _root: SimpleNamespace(
            result=result,
            reusable_run_head="",
        )
    )


def test_large_focused_plan_narrows_before_validation(registry, history_store):
    tight = replace(registry, edit_loop_budget_seconds=1.0)
    profile = profile_for_execution_id(tight, "gate:focused-cluster")
    steps = (
        ("pytest", [sys.executable, "-m", "pytest"] + ["tests/x.py"] * 5000),
        ("validator", echo_command("validate")),
    )
    child_plans = preview_focused_child_plans(
        ROOT,
        tight,
        steps=steps,
        mode="cluster",
        test_file_count=5000,
    )
    with patch(
        "scripts.execution_control.admission._load_ci_necessity",
        return_value=_fake_necessity(),
    ):
        admission, parent_plan = assess_gate_admission(
            ROOT,
            execution_id="gate:focused-cluster",
            profile=profile,
            registry=tight,
            history=history_store,
            child_plans=child_plans,
            command=[sys.executable, "scripts/run_focused_tests.py"],
            mode="cluster",
            required=False,
            test_file_count=5000,
        )
    assert admission.decision == AdmissionDecision.NARROW
    assert parent_plan is not None
    assert parent_plan.admission_decision == AdmissionDecision.NARROW.value
    assert admission.reason == "edit-loop-budget-exceeded"


def test_small_focused_plan_runs(registry, history_store):
    profile = profile_for_execution_id(registry, "gate:focused-cluster")
    steps = (("pytest", echo_command("ok")),)
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
    assert parent_plan.admission_decision == AdmissionDecision.RUN.value


def test_required_final_gate_remains_allowed(registry, history_store):
    profile = profile_for_execution_id(registry, "gate:full-ci")
    from scripts.ci_runner import _full_ci_preview_steps
    from scripts.execution_control.gate_flow import preview_ci_child_plans

    child_plans = preview_ci_child_plans(
        ROOT,
        registry,
        steps=_full_ci_preview_steps(sys.executable),
    )
    admission, parent_plan = assess_gate_admission(
        ROOT,
        execution_id="gate:full-ci",
        profile=profile,
        registry=registry,
        history=history_store,
        child_plans=child_plans,
        command=[sys.executable, "scripts/ci_runner.py"],
        mode="full-ci",
        required=True,
        coverage=True,
        packaging=True,
    )
    assert admission.decision == AdmissionDecision.RUN
    assert parent_plan is not None
    assert parent_plan.planned_child_count == len(child_plans)
