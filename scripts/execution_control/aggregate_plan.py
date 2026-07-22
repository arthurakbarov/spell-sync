"""Aggregate parent gate plans from concrete child previews."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .context import build_context
from .identity import (
    build_workload_payload,
    normalized_signature,
    policy_fingerprint,
    workload_fingerprint,
)
from .models import ExecutionPlan
from .prediction import _round_up_seconds
from .registry import ExecutionBudgetRegistry, Profile


def orchestration_overhead_seconds(child_expected_sum: float) -> float:
    return max(10.0, child_expected_sum * 0.1)


def child_plan_digest(child_plans: tuple[ExecutionPlan, ...]) -> str:
    payload = [
        {
            "executionId": plan.execution_id,
            "expectedSeconds": plan.expected_seconds,
            "softSeconds": plan.soft_seconds,
            "hardSeconds": plan.hard_seconds,
            "workloadFingerprint": plan.workload_fingerprint,
        }
        for plan in child_plans
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AggregateSummary:
    planned_child_count: int
    planned_expected_sum: float
    planned_soft_sum: float
    planned_hard_sum: float
    orchestration_overhead_estimate: float
    child_plan_digest: str


def summarize_child_plans(child_plans: tuple[ExecutionPlan, ...]) -> AggregateSummary:
    expected_sum = sum(plan.expected_seconds for plan in child_plans)
    soft_sum = sum(plan.soft_seconds for plan in child_plans)
    hard_sum = sum(plan.hard_seconds for plan in child_plans)
    overhead = orchestration_overhead_seconds(expected_sum)
    return AggregateSummary(
        planned_child_count=len(child_plans),
        planned_expected_sum=expected_sum,
        planned_soft_sum=soft_sum,
        planned_hard_sum=hard_sum,
        orchestration_overhead_estimate=overhead,
        child_plan_digest=child_plan_digest(child_plans),
    )


def build_aggregate_gate_plan(
    *,
    root: Path,
    run_id: str,
    execution_id: str,
    profile: Profile,
    registry: ExecutionBudgetRegistry,
    child_plans: tuple[ExecutionPlan, ...],
    command: list[str],
    mode: str,
    admission_decision: str,
    test_file_count: int = 0,
    coverage: bool = False,
    tui: bool = False,
    packaging: bool = False,
) -> ExecutionPlan:
    summary = summarize_child_plans(child_plans)
    parent_expected = _round_up_seconds(
        summary.planned_expected_sum + summary.orchestration_overhead_estimate
    )
    soft_candidates = [
        profile.initial_soft_seconds,
        summary.planned_soft_sum + summary.orchestration_overhead_estimate,
        parent_expected * 1.5,
    ]
    parent_soft = _round_up_seconds(max(soft_candidates))
    hard_candidates = [
        profile.initial_hard_seconds,
        summary.planned_hard_sum + summary.orchestration_overhead_estimate,
        parent_soft * 1.5,
        parent_soft + profile.termination_grace_seconds,
    ]
    parent_hard = min(
        profile.hard_cap_seconds,
        registry.global_hard_cap_seconds,
        _round_up_seconds(max(hard_candidates)),
    )
    stall_seconds: float | None = None
    if profile.progress_contract:
        child_stalls = [plan.stall_seconds for plan in child_plans if plan.stall_seconds]
        if child_stalls:
            stall_seconds = min(profile.stall_cap_seconds, max(child_stalls))

    context = build_context(
        execution_mode=mode,
        test_file_count=test_file_count,
        coverage=coverage,
        tui=tui,
        packaging=packaging,
    )
    workload_payload = build_workload_payload(
        root=root,
        execution_id=execution_id,
        command=command,
        mode=mode,
        test_file_count=test_file_count,
        cluster_ids=(summary.child_plan_digest[:16],),
        coverage=coverage,
        tui=tui,
        packaging=packaging,
    )
    workload_fp = workload_fingerprint(execution_id=execution_id, workload=workload_payload)
    policy_fp = policy_fingerprint(registry, profile.profile_id)
    signature = normalized_signature(
        execution_id=execution_id,
        workload_fingerprint_value=workload_fp,
        context_signature=context.signature(),
    )
    sample_count = max((plan.sample_count for plan in child_plans), default=0)
    confidence = "high" if sample_count >= 10 else "medium" if sample_count >= 3 else "none"
    return ExecutionPlan(
        run_id=run_id,
        execution_id=execution_id,
        profile_id=profile.profile_id,
        normalized_signature=signature,
        workload_fingerprint=workload_fp,
        policy_fingerprint=policy_fp,
        expected_seconds=parent_expected,
        soft_seconds=min(parent_soft, parent_hard),
        stall_seconds=stall_seconds,
        hard_seconds=parent_hard,
        diagnostic_hard_seconds=profile.diagnostic_hard_seconds,
        termination_grace_seconds=profile.termination_grace_seconds,
        progress_contract_id=profile.progress_contract or None,
        termination_policy_id="owned-process-group",
        prediction_source="aggregate-child-plans",
        confidence=confidence,
        sample_count=sample_count,
        admission_decision=admission_decision,
        context_signature=context.signature(),
        child_plan_digest=summary.child_plan_digest,
        planned_child_count=summary.planned_child_count,
        planned_expected_sum=summary.planned_expected_sum,
        planned_soft_sum=summary.planned_soft_sum,
        orchestration_overhead_estimate=summary.orchestration_overhead_estimate,
        planned_child_expected_sum=summary.planned_expected_sum,
        planned_orchestration_overhead=summary.orchestration_overhead_estimate,
    )
