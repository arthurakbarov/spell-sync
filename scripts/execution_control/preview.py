"""Pure execution-plan preview without subprocess or side effects."""

from __future__ import annotations

from pathlib import Path

from .context import build_context
from .history import HistoryStore
from .identity import (
    build_workload_payload,
    normalized_signature,
    policy_fingerprint,
    workload_fingerprint,
)
from .models import ExecutionPlan
from .prediction import build_execution_plan
from .registry import ExecutionBudgetRegistry, Profile, profile_for_execution_id


def preview_execution_plan(
    root: Path,
    registry: ExecutionBudgetRegistry,
    *,
    execution_id: str,
    command: list[str],
    mode: str,
    test_file_count: int = 0,
    test_node_count: int = 0,
    cluster_ids: tuple[str, ...] = (),
    coverage: bool = False,
    tui: bool = False,
    packaging: bool = False,
    run_id: str = "preview",
    admission_decision: str = "preview",
) -> ExecutionPlan:
    """Build a child ExecutionPlan without subprocess, lease, or artifact writes."""
    profile = profile_for_execution_id(registry, execution_id)
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
    history = HistoryStore.open()
    return build_execution_plan(
        run_id=run_id,
        execution_id=execution_id,
        profile=profile,
        registry=registry,
        history=history,
        workload_fingerprint_value=workload_fp,
        policy_fingerprint_value=policy_fp,
        normalized_signature_value=signature,
        context=context,
        admission_decision=admission_decision,
    )


def preview_execution_plan_with_profile(
    root: Path,
    registry: ExecutionBudgetRegistry,
    profile: Profile,
    *,
    execution_id: str,
    command: list[str],
    mode: str,
    test_file_count: int = 0,
    test_node_count: int = 0,
    cluster_ids: tuple[str, ...] = (),
    coverage: bool = False,
    tui: bool = False,
    packaging: bool = False,
    run_id: str = "preview",
    admission_decision: str = "preview",
) -> ExecutionPlan:
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
    history = HistoryStore.open()
    return build_execution_plan(
        run_id=run_id,
        execution_id=execution_id,
        profile=profile,
        registry=registry,
        history=history,
        workload_fingerprint_value=workload_fp,
        policy_fingerprint_value=policy_fp,
        normalized_signature_value=signature,
        context=context,
        admission_decision=admission_decision,
    )
