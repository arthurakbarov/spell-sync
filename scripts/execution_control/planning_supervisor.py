"""Bounded planning supervisor without final gate lease."""

from __future__ import annotations

from pathlib import Path

from .controller import ExecutionController
from .models import ExecutionStatus


def run_planning_supervisor(
    controller: ExecutionController,
    *,
    planner_execution_id: str,
    command: list[str],
    mode: str,
    cwd: Path | None = None,
) -> tuple[int, str]:
    """Run a bounded planner child without acquiring a parent gate lease."""
    plan, state = controller.prepare_plan(
        execution_id=planner_execution_id,
        command=command,
        mode=mode,
        required=False,
    )
    if plan is None:
        return 0 if state == ExecutionStatus.REUSED.value else 1, state
    try:
        execution = controller.run(
            plan,
            command,
            cwd=cwd or controller.root,
            active_child=planner_execution_id,
            release_lease=True,
        )
    finally:
        controller.history.release_lease(plan.normalized_signature)
    return execution.exit_code, "run"
