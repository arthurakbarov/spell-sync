"""Execution runtime reporting."""

from __future__ import annotations

from .models import ExecutionPlan


def print_plan(plan: ExecutionPlan) -> None:
    print(f"EXECUTION_ID={plan.execution_id}")
    print(f"EXECUTION_PROFILE={plan.profile_id}")
    print(f"EXECUTION_EXPECTED_SECONDS={plan.expected_seconds:.0f}")
    print(f"EXECUTION_SOFT_SECONDS={plan.soft_seconds:.0f}")
    if plan.stall_seconds is None:
        print("EXECUTION_STALL_SECONDS=disabled")
    else:
        print(f"EXECUTION_STALL_SECONDS={plan.stall_seconds:.0f}")
    print(f"EXECUTION_HARD_SECONDS={plan.hard_seconds:.0f}")
    print(f"EXECUTION_INTERACTIVE_PROMPTS={plan.expected_prompt_count}")
    print(f"EXECUTION_INTERACTIVE_ALLOWANCE_SECONDS={plan.interactive_allowance_seconds:.0f}")
    print(f"EXECUTION_WALL_HARD_SECONDS={plan.wall_hard_seconds:.0f}")
    print(f"EXECUTION_DIAGNOSTIC_HARD_SECONDS={plan.diagnostic_hard_seconds:.0f}")
    print(f"EXECUTION_BUDGET_SOURCE={plan.prediction_source}")
    print(f"EXECUTION_CONFIDENCE={plan.confidence}")
    print(f"EXECUTION_SAMPLE_COUNT={plan.sample_count}")
    print(f"EXECUTION_ADMISSION_DECISION={plan.admission_decision}")


def print_soft_overrun(
    *,
    plan: ExecutionPlan,
    elapsed: float,
    active_child: str | None,
    progress_age: float,
) -> None:
    print("EXECUTION_STATE=running-over-soft")
    print(f"EXECUTION_ACTIVE_CHILD={active_child or ''}")
    print(f"EXECUTION_ELAPSED_SECONDS={elapsed:.2f}")
    print(f"EXECUTION_LAST_PROGRESS_AGE_SECONDS={progress_age:.2f}")
    if plan.stall_seconds is not None:
        remaining = max(0.0, plan.stall_seconds - progress_age)
        print(f"EXECUTION_STALL_REMAINING_SECONDS={remaining:.2f}")
    print(f"EXECUTION_HARD_REMAINING_SECONDS={max(0.0, plan.wall_hard_seconds - elapsed):.2f}")


def print_result(
    *,
    result: str,
    exit_code: int,
    duration: float,
    active_child: str | None,
    history_updated: bool,
    learning_accepted: bool,
    waiting_seconds: float = 0.0,
) -> None:
    print(f"EXECUTION_RESULT={result}")
    print(f"EXECUTION_EXIT={exit_code}")
    print(f"EXECUTION_DURATION_SECONDS={duration:.2f}")
    print(f"EXECUTION_WAITING_SECONDS={waiting_seconds:.2f}")
    print(f"EXECUTION_ACTIVE_CHILD={active_child or ''}")
    print(f"EXECUTION_HISTORY_UPDATED={'true' if history_updated else 'false'}")
    print(f"EXECUTION_LEARNING_ACCEPTED={'true' if learning_accepted else 'false'}")
