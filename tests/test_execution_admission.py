"""Tests for execution admission integrated with CI necessity."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.admission import assess_admission  # noqa: E402
from scripts.execution_control.models import AdmissionDecision  # noqa: E402


@dataclass
class _FakeNecessity:
    result: str
    reusable_run_head: str = ""


def _mock_necessity(result: str, reusable_run_head: str = ""):
    fake_module = SimpleNamespace(
        assess_ci_necessity=lambda _root: _FakeNecessity(result, reusable_run_head),
    )
    return patch(
        "scripts.execution_control.admission._load_ci_necessity",
        return_value=fake_module,
    )


def test_reuse_when_no_action_and_not_required(registry, history_store):
    profile = registry.profiles["focused-module"]
    with _mock_necessity("no-action"):
        plan, execution_plan = assess_admission(
            ROOT,
            execution_id=profile.execution_id,
            profile=profile,
            registry=registry,
            history=history_store,
            command=["python3", "-m", "pytest", "tests/"],
            mode="exact",
            required=False,
        )
    assert plan.decision == AdmissionDecision.REUSE
    assert plan.reason == "current-evidence-valid"
    assert execution_plan is None


def test_reuse_full_ci_when_lightweight_sufficient(registry, history_store):
    profile = registry.profiles["full-ci"]
    with _mock_necessity("lightweight-sufficient", reusable_run_head="abc123"):
        plan, execution_plan = assess_admission(
            ROOT,
            execution_id=profile.execution_id,
            profile=profile,
            registry=registry,
            history=history_store,
            command=["scripts/ci.sh"],
            mode="full",
            required=False,
        )
    assert plan.decision == AdmissionDecision.REUSE
    assert plan.reason == "lightweight-sufficient"
    assert plan.reusable_run_head == "abc123"
    assert execution_plan is None


def test_run_when_full_required(registry, history_store):
    profile = registry.profiles["full-ci"]
    with _mock_necessity("lightweight-sufficient"):
        plan, execution_plan = assess_admission(
            ROOT,
            execution_id=profile.execution_id,
            profile=profile,
            registry=registry,
            history=history_store,
            command=["scripts/ci.sh"],
            mode="full",
            required=True,
        )
    assert plan.decision == AdmissionDecision.RUN
    assert execution_plan is not None


def test_narrow_when_edit_loop_budget_exceeded(registry, history_store):
    profile = registry.profiles["focused-module"]
    tight_registry = replace(registry, edit_loop_budget_seconds=1.0)
    with _mock_necessity("full-required"):
        plan, execution_plan = assess_admission(
            ROOT,
            execution_id=profile.execution_id,
            profile=profile,
            registry=tight_registry,
            history=history_store,
            command=["python3", "-m", "pytest", "tests/"],
            mode="exact",
            required=False,
        )
    assert plan.decision == AdmissionDecision.NARROW
    assert plan.reason == "edit-loop-budget-exceeded"
    assert execution_plan is not None
    assert plan.total_expected_seconds > tight_registry.edit_loop_budget_seconds


def test_run_for_full_required_necessity(registry, history_store):
    profile = registry.profiles["focused-cluster"]
    with _mock_necessity("full-required"):
        plan, execution_plan = assess_admission(
            ROOT,
            execution_id=profile.execution_id,
            profile=profile,
            registry=registry,
            history=history_store,
            command=["python3", "scripts/run_focused_tests.py"],
            mode="cluster",
            required=False,
        )
    assert plan.decision == AdmissionDecision.RUN
    assert plan.reason == "execution-required"
    assert execution_plan is not None
    assert plan.required_checks == (profile.execution_id,)
