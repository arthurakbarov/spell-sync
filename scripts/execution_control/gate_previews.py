"""Two-stage gate flow: bounded planner → child previews → aggregate admission."""

from __future__ import annotations

from pathlib import Path

from .gate_controller import ActiveGate, GateController
from .mappings import ci_check_execution_id, snapshot_step_execution_id
from .models import ExecutionPlan
from .plan_preview import preview_execution_plan
from .planning_supervisor import run_planning_supervisor
from .registry import ExecutionBudgetRegistry, load_registry, profile_for_execution_id

FOCUSED_STEP_EXECUTION_IDS: dict[str, str] = {
    "validator": "focused:validators",
    "pytest": "focused:pytest",
    "ruff-check": "focused:static",
    "ruff-format": "focused:static",
    "mypy": "focused:static",
}


def focused_step_execution_id(step_kind: str) -> str:
    return FOCUSED_STEP_EXECUTION_IDS.get(step_kind, "focused:validators")


def pre_final_step_execution_id(name: str) -> str:
    if name == "registry":
        return "pre-final:validators"
    if name.startswith("validator:"):
        return "pre-final:validators"
    if name.startswith("focused-pytest") or name == "focused-pytest":
        return "pre-final:pytest"
    if name.startswith("ruff-check:"):
        return "pre-final:ruff-check"
    if name.startswith("ruff-format:"):
        return "pre-final:ruff-format"
    if name.startswith("mypy:"):
        return "pre-final:mypy"
    if name.endswith(".sh") or name.endswith(".py"):
        return "pre-final:validators"
    return "pre-final:validators"


def preview_focused_child_plans(
    root: Path,
    registry: ExecutionBudgetRegistry,
    *,
    steps: tuple[tuple[str, list[str]], ...],
    mode: str,
    test_file_count: int = 0,
    run_id: str = "preview",
) -> tuple[ExecutionPlan, ...]:
    return tuple(
        preview_execution_plan(
            root,
            registry,
            execution_id=focused_step_execution_id(kind),
            command=command,
            mode=mode,
            test_file_count=test_file_count,
            run_id=run_id,
        )
        for kind, command in steps
    )


def preview_pre_final_child_plans(
    root: Path,
    registry: ExecutionBudgetRegistry,
    *,
    steps: tuple[tuple[str, list[str]], ...],
    mode: str = "pre-final",
    run_id: str = "preview",
) -> tuple[ExecutionPlan, ...]:
    return tuple(
        preview_execution_plan(
            root,
            registry,
            execution_id=pre_final_step_execution_id(name),
            command=command,
            mode=mode,
            run_id=run_id,
        )
        for name, command in steps
    )


def preview_ci_child_plans(
    root: Path,
    registry: ExecutionBudgetRegistry,
    *,
    steps: tuple[tuple[str, list[str], bool, bool, bool], ...],
    mode: str = "full-ci",
    run_id: str = "preview",
) -> tuple[ExecutionPlan, ...]:
    plans: list[ExecutionPlan] = []
    for step_id, argv, coverage, tui, packaging in steps:
        plans.append(
            preview_execution_plan(
                root,
                registry,
                execution_id=ci_check_execution_id(step_id),
                command=argv,
                mode=mode,
                coverage=coverage,
                tui=tui,
                packaging=packaging,
                run_id=run_id,
            )
        )
    return tuple(plans)


def preview_snapshot_child_plans(
    root: Path,
    registry: ExecutionBudgetRegistry,
    *,
    steps: tuple[tuple[str, list[str]], ...],
    workspace_root: Path,
    output_path: Path,
    mode: str = "snapshot-tests",
    run_id: str = "preview",
) -> tuple[ExecutionPlan, ...]:
    del workspace_root, output_path
    return tuple(
        preview_execution_plan(
            root,
            registry,
            execution_id=snapshot_step_execution_id(step_id),
            command=command,
            mode=mode,
            run_id=run_id,
        )
        for step_id, command in steps
    )


def run_bounded_planner(
    controller: GateController,
    *,
    planner_execution_id: str,
    command: list[str],
    mode: str,
    cwd: Path | None = None,
) -> tuple[int, str]:
    return run_planning_supervisor(
        controller,
        planner_execution_id=planner_execution_id,
        command=command,
        mode=mode,
        cwd=cwd,
    )


def open_gate_after_previews(
    gate_controller: GateController,
    *,
    execution_id: str,
    command: list[str],
    mode: str,
    child_plans: tuple[ExecutionPlan, ...],
    required: bool = False,
    test_file_count: int = 0,
    coverage: bool = False,
    tui: bool = False,
    packaging: bool = False,
) -> tuple[ActiveGate | None, str, tuple[ExecutionPlan, ...], ExecutionPlan | None]:
    parent_plan, state = gate_controller.prepare_gate_from_children(
        execution_id=execution_id,
        command=command,
        mode=mode,
        child_plans=child_plans,
        required=required,
        test_file_count=test_file_count,
        coverage=coverage,
        tui=tui,
        packaging=packaging,
    )
    if parent_plan is None:
        return None, state, child_plans, None
    gate, gate_state = gate_controller.begin_gate_with_plan(
        parent_plan,
        child_plans=child_plans,
    )
    return gate, gate_state, child_plans, parent_plan


def gate_controller_for(root: Path) -> GateController:
    return GateController.open_gate_controller(root)


def registry_for(root: Path) -> ExecutionBudgetRegistry:
    from .registry import REGISTRY_REL_PATH

    return load_registry(root / REGISTRY_REL_PATH)


def profile_for_gate(root: Path, execution_id: str):
    return profile_for_execution_id(registry_for(root), execution_id)
