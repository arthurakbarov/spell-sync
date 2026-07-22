"""Execution admission planning integrated with CI necessity."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

from .context import build_context
from .history import HistoryStore
from .identity import (
    build_workload_payload,
    normalized_signature,
    policy_fingerprint,
    workload_fingerprint,
)
from .models import AdmissionDecision
from .prediction import build_execution_plan
from .registry import ExecutionBudgetRegistry, Profile


@dataclass(frozen=True, slots=True)
class NarrowReplacementPlan:
    required_checks: tuple[str, ...]
    deferred_checks: tuple[str, ...]
    suggested_execution_id: str
    suggested_command_key: str
    predicted_replacement_cost: float


def narrow_replacement_plan(
    *,
    execution_id: str,
    mode: str,
    admission: AdmissionPlan,
    plan: object | None,
) -> NarrowReplacementPlan:
    del mode
    predicted = admission.total_expected_seconds
    if execution_id == "gate:focused-cluster":
        return NarrowReplacementPlan(
            required_checks=("gate:focused-module", "focused:pytest"),
            deferred_checks=("gate:focused-cluster", "focused:static"),
            suggested_execution_id="gate:focused-module",
            suggested_command_key="focused-module",
            predicted_replacement_cost=max(1.0, predicted * 0.4),
        )
    if execution_id == "gate:focused-module":
        return NarrowReplacementPlan(
            required_checks=("focused:validators",),
            deferred_checks=(execution_id, "focused:pytest", "focused:static"),
            suggested_execution_id="focused:validators",
            suggested_command_key="focused-validators",
            predicted_replacement_cost=max(1.0, predicted * 0.2),
        )
    if plan is not None and hasattr(plan, "expected_seconds"):
        predicted = float(getattr(plan, "expected_seconds", predicted))
    return NarrowReplacementPlan(
        required_checks=admission.required_checks,
        deferred_checks=admission.optional_checks,
        suggested_execution_id=execution_id,
        suggested_command_key=execution_id.split(":")[-1],
        predicted_replacement_cost=predicted,
    )


@dataclass(frozen=True, slots=True)
class AdmissionPlan:
    decision: AdmissionDecision
    reason: str
    required_checks: tuple[str, ...]
    optional_checks: tuple[str, ...]
    total_expected_seconds: float
    total_soft_seconds: float
    reusable_run_head: str = ""


def _load_ci_necessity(root: Path):
    spec = importlib.util.spec_from_file_location(
        "check_ci_necessity",
        root / "scripts" / "check-ci-necessity.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    assert spec.name
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def assess_admission(
    root: Path,
    *,
    execution_id: str,
    profile: Profile,
    registry: ExecutionBudgetRegistry,
    history: HistoryStore,
    command: list[str],
    mode: str,
    required: bool = False,
    test_file_count: int = 0,
    test_node_count: int = 0,
    cluster_ids: tuple[str, ...] = (),
    coverage: bool = False,
    tui: bool = False,
    packaging: bool = False,
) -> tuple[AdmissionPlan, object | None]:
    necessity = _load_ci_necessity(root).assess_ci_necessity(root)
    context = build_context(
        execution_mode=mode,
        test_file_count=test_file_count,
        test_node_count=test_node_count,
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
        test_node_count=test_node_count,
        cluster_ids=cluster_ids,
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
    run_id = history.new_run_id()
    if necessity.result == "no-action" and not required:
        return (
            AdmissionPlan(
                decision=AdmissionDecision.REUSE,
                reason="current-evidence-valid",
                required_checks=(execution_id,),
                optional_checks=(),
                total_expected_seconds=0.0,
                total_soft_seconds=0.0,
            ),
            None,
        )
    if (
        necessity.result == "lightweight-sufficient"
        and execution_id.startswith("gate:full-ci")
        and not required
    ):
        return (
            AdmissionPlan(
                decision=AdmissionDecision.REUSE,
                reason="lightweight-sufficient",
                required_checks=(execution_id,),
                optional_checks=(),
                total_expected_seconds=0.0,
                total_soft_seconds=0.0,
                reusable_run_head=necessity.reusable_run_head,
            ),
            None,
        )
    plan = build_execution_plan(
        run_id=run_id,
        execution_id=execution_id,
        profile=profile,
        registry=registry,
        history=history,
        workload_fingerprint_value=workload_fp,
        policy_fingerprint_value=policy_fp,
        normalized_signature_value=signature,
        context=context,
        admission_decision=AdmissionDecision.RUN.value,
    )
    total_expected = plan.expected_seconds
    total_soft = plan.soft_seconds
    if (
        not required
        and total_expected > registry.edit_loop_budget_seconds
        and execution_id.startswith("gate:focused")
    ):
        narrow_plan = build_execution_plan(
            run_id=run_id,
            execution_id=execution_id,
            profile=profile,
            registry=registry,
            history=history,
            workload_fingerprint_value=workload_fp,
            policy_fingerprint_value=policy_fp,
            normalized_signature_value=signature,
            context=context,
            admission_decision=AdmissionDecision.NARROW.value,
        )
        return (
            AdmissionPlan(
                decision=AdmissionDecision.NARROW,
                reason="edit-loop-budget-exceeded",
                required_checks=(execution_id,),
                optional_checks=(),
                total_expected_seconds=total_expected,
                total_soft_seconds=total_soft,
            ),
            narrow_plan,
        )
    return (
        AdmissionPlan(
            decision=AdmissionDecision.RUN,
            reason="execution-required",
            required_checks=(execution_id,),
            optional_checks=(),
            total_expected_seconds=total_expected,
            total_soft_seconds=total_soft,
        ),
        plan,
    )


def timing_block_from_plan(plan) -> dict[str, object]:
    return {
        "executionId": plan.execution_id,
        "profileId": plan.profile_id,
        "expectedSeconds": plan.expected_seconds,
        "softSeconds": plan.soft_seconds,
        "stallSeconds": plan.stall_seconds,
        "hardSeconds": plan.hard_seconds,
        "predictionSource": plan.prediction_source,
        "confidence": plan.confidence,
        "sampleCount": plan.sample_count,
    }
