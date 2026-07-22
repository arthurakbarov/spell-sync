"""Aggregate parent plans must derive timing from concrete child previews."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.aggregate_plan import (  # noqa: E402
    build_aggregate_gate_plan,
    orchestration_overhead_seconds,
    summarize_child_plans,
)
from scripts.execution_control.preview import preview_execution_plan  # noqa: E402
from tests.conftest_execution import echo_command  # noqa: E402


def test_child_plan_sum_drives_parent_expected(registry):
    children = tuple(
        preview_execution_plan(
            ROOT,
            registry,
            execution_id="focused:pytest",
            command=echo_command(f"child-{index}"),
            mode="cluster",
            test_file_count=index + 1,
        )
        for index in range(5)
    )
    single = (children[0],)
    multi_summary = summarize_child_plans(children)
    single_summary = summarize_child_plans(single)
    assert multi_summary.planned_expected_sum != single_summary.planned_expected_sum
    assert multi_summary.planned_child_count == 5

    overhead = orchestration_overhead_seconds(multi_summary.planned_expected_sum)
    profile = registry.profiles["focused-cluster"]
    parent = build_aggregate_gate_plan(
        root=ROOT,
        run_id="aggregate-test",
        execution_id="gate:focused-cluster",
        profile=profile,
        registry=registry,
        child_plans=children,
        command=["python3", "scripts/run_focused_tests.py"],
        mode="cluster",
        admission_decision="run",
        test_file_count=5000,
    )
    assert parent.planned_child_expected_sum == multi_summary.planned_expected_sum
    assert parent.planned_orchestration_overhead == overhead
    assert parent.expected_seconds == round(multi_summary.planned_expected_sum + overhead)
    assert (
        abs(
            parent.expected_seconds
            - (parent.planned_child_expected_sum + parent.planned_orchestration_overhead)
        )
        <= 1.0
    )


def test_single_child_aggregate_differs_from_empty(registry):
    child = preview_execution_plan(
        ROOT,
        registry,
        execution_id="focused:pytest",
        command=echo_command("solo"),
        mode="cluster",
        test_file_count=1,
    )
    profile = registry.profiles["focused-cluster"]
    parent = build_aggregate_gate_plan(
        root=ROOT,
        run_id="aggregate-solo",
        execution_id="gate:focused-cluster",
        profile=profile,
        registry=registry,
        child_plans=(child,),
        command=["python3", "scripts/run_focused_tests.py"],
        mode="cluster",
        admission_decision="run",
        test_file_count=1,
    )
    assert parent.planned_child_count == 1
    assert parent.child_plan_digest is not None
    assert parent.expected_seconds >= child.expected_seconds
