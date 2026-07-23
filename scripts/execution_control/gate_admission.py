"""Gate admission after concrete child plan previews."""

from __future__ import annotations

from pathlib import Path

from .admission import AdmissionPlan, narrow_replacement_plan
from .aggregate_plan import build_aggregate_gate_plan, summarize_child_plans
from .history import HistoryStore
from .models import AdmissionDecision, ExecutionPlan
from .registry import ExecutionBudgetRegistry, Profile, profile_for_execution_id
from .session import current_session_test_share


def assess_gate_admission(
    root: Path,
    *,
    execution_id: str,
    profile: Profile,
    registry: ExecutionBudgetRegistry,
    history: HistoryStore,
    child_plans: tuple[ExecutionPlan, ...],
    command: list[str],
    mode: str,
    required: bool = False,
    test_file_count: int = 0,
    coverage: bool = False,
    tui: bool = False,
    packaging: bool = False,
) -> tuple[AdmissionPlan, ExecutionPlan | None]:
    summary = summarize_child_plans(child_plans, history=history, execution_id=execution_id)
    aggregate_expected = summary.planned_expected_sum + summary.orchestration_overhead_estimate
    aggregate_soft = summary.planned_soft_sum + summary.orchestration_overhead_estimate
    required_checks = tuple({plan.execution_id for plan in child_plans})
    optional_checks: tuple[str, ...] = ()
    run_id = history.new_run_id()

    if not required and execution_id.startswith("gate:focused"):
        if aggregate_expected > registry.edit_loop_budget_seconds:
            narrow_plan = build_aggregate_gate_plan(
                root=root,
                run_id=run_id,
                execution_id=execution_id,
                profile=profile,
                registry=registry,
                child_plans=child_plans,
                command=command,
                mode=mode,
                admission_decision=AdmissionDecision.NARROW.value,
                test_file_count=test_file_count,
                history=history,
            )
            admission = AdmissionPlan(
                decision=AdmissionDecision.NARROW,
                reason="edit-loop-budget-exceeded",
                required_checks=required_checks,
                optional_checks=optional_checks,
                total_expected_seconds=aggregate_expected,
                total_soft_seconds=aggregate_soft,
            )
            return admission, narrow_plan
        share = current_session_test_share()
        if share is not None and share > registry.session_test_time_share_warn:
            narrow_plan = build_aggregate_gate_plan(
                root=root,
                run_id=run_id,
                execution_id=execution_id,
                profile=profile,
                registry=registry,
                child_plans=child_plans,
                command=command,
                mode=mode,
                admission_decision=AdmissionDecision.NARROW.value,
                test_file_count=test_file_count,
                history=history,
            )
            admission = AdmissionPlan(
                decision=AdmissionDecision.NARROW,
                reason="session-test-time-share-exceeded",
                required_checks=required_checks,
                optional_checks=optional_checks,
                total_expected_seconds=aggregate_expected,
                total_soft_seconds=aggregate_soft,
            )
            return admission, narrow_plan

    parent_plan = build_aggregate_gate_plan(
        root=root,
        run_id=run_id,
        execution_id=execution_id,
        profile=profile,
        registry=registry,
        child_plans=child_plans,
        command=command,
        mode=mode,
        admission_decision=AdmissionDecision.RUN.value,
        test_file_count=test_file_count,
        coverage=coverage,
        tui=tui,
        packaging=packaging,
        history=history,
    )
    admission = AdmissionPlan(
        decision=AdmissionDecision.RUN,
        reason="execution-required",
        required_checks=required_checks,
        optional_checks=optional_checks,
        total_expected_seconds=aggregate_expected,
        total_soft_seconds=aggregate_soft,
    )
    return admission, parent_plan


def emit_narrow_replacement(
    *,
    execution_id: str,
    mode: str,
    admission: AdmissionPlan,
    plan: ExecutionPlan | None,
) -> None:
    replacement = narrow_replacement_plan(
        execution_id=execution_id,
        mode=mode,
        admission=admission,
        plan=plan,
    )
    print(f"EXECUTION_REPLACEMENT_REQUIRED_CHECKS={','.join(replacement.required_checks)}")
    print(f"EXECUTION_REPLACEMENT_DEFERRED_CHECKS={','.join(replacement.deferred_checks)}")
    print(f"EXECUTION_REPLACEMENT_EXECUTION_ID={replacement.suggested_execution_id}")
    print(f"EXECUTION_REPLACEMENT_COMMAND_KEY={replacement.suggested_command_key}")
    print(f"EXECUTION_REPLACEMENT_PREDICTED_COST={replacement.predicted_replacement_cost:.2f}")


def gate_profile_for_execution_id(
    registry: ExecutionBudgetRegistry,
    execution_id: str,
) -> Profile:
    return profile_for_execution_id(registry, execution_id)
