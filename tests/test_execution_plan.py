"""Execution plan immutability and serialization tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.context import build_context  # noqa: E402
from scripts.execution_control.identity import (  # noqa: E402
    build_workload_payload,
    normalized_signature,
    policy_fingerprint,
    workload_fingerprint,
)
from scripts.execution_control.models import ExecutionPlan  # noqa: E402
from scripts.execution_control.prediction import build_execution_plan  # noqa: E402


def _sample_plan(**overrides) -> ExecutionPlan:
    base = dict(
        run_id="run-1",
        execution_id="ci:pytest",
        profile_id="ci-child",
        normalized_signature="abc123",
        workload_fingerprint="workload",
        policy_fingerprint="policy",
        expected_seconds=60.0,
        soft_seconds=120.0,
        stall_seconds=None,
        hard_seconds=300.0,
        diagnostic_hard_seconds=10.0,
        termination_grace_seconds=5.0,
        progress_contract_id=None,
        termination_policy_id="owned-process-group",
        prediction_source="registry-default",
        confidence="none",
        sample_count=0,
        admission_decision="run",
    )
    base.update(overrides)
    return ExecutionPlan(**base)


def test_execution_plan_is_immutable():
    plan = _sample_plan()
    with pytest.raises(FrozenInstanceError):
        plan.expected_seconds = 999.0  # type: ignore[misc]


def test_execution_plan_serializes_bounded_keys():
    plan = _sample_plan(stall_seconds=45.0, progress_contract_id="ci-child-transition")
    payload = plan.to_json_dict()
    assert payload["executionId"] == "ci:pytest"
    assert payload["stallSeconds"] == 45.0
    assert payload["runId"] == "run-1"
    assert len(payload) <= 20


def test_to_json_dict_round_trip_keys():
    plan = _sample_plan(stall_seconds=30.0, progress_contract_id="ci-child-transition")
    payload = plan.to_json_dict()
    assert payload["normalizedSignature"] == plan.normalized_signature
    assert payload["workloadFingerprint"] == plan.workload_fingerprint
    assert payload["policyFingerprint"] == plan.policy_fingerprint
    assert payload["admissionDecision"] == plan.admission_decision


def test_build_execution_plan_from_registry(registry, history):
    profile = registry.profiles["focused-module"]
    context = build_context(execution_mode="exact", test_file_count=2)
    workload = build_workload_payload(
        root=ROOT,
        execution_id=profile.execution_id,
        command=["python3", "-m", "pytest", "tests/"],
        mode="exact",
        test_file_count=2,
    )
    workload_fp = workload_fingerprint(execution_id=profile.execution_id, workload=workload)
    policy_fp = policy_fingerprint(registry, profile.profile_id)
    signature = normalized_signature(
        execution_id=profile.execution_id,
        workload_fingerprint_value=workload_fp,
        context_signature=context.signature(),
    )
    plan = build_execution_plan(
        run_id=history.new_run_id(),
        execution_id=profile.execution_id,
        profile=profile,
        registry=registry,
        history=history,
        workload_fingerprint_value=workload_fp,
        policy_fingerprint_value=policy_fp,
        normalized_signature_value=signature,
        context=context,
        admission_decision="run",
    )
    assert plan.execution_id == "gate:focused-module"
    assert plan.expected_seconds >= profile.initial_expected_seconds
    assert plan.soft_seconds > plan.expected_seconds
    assert plan.hard_seconds >= plan.soft_seconds
