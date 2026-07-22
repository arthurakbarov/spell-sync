"""Live soft-overrun reporting tests."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.process_tree import run_owned_command  # noqa: E402
from tests.conftest_execution import spam_command  # noqa: E402


def test_soft_marker_emitted_before_completion(isolated_state_dir, capsys):
    del isolated_state_dir

    from scripts.execution_control.models import ExecutionPlan

    plan = ExecutionPlan(
        run_id="soft-run",
        execution_id="focused:pytest",
        profile_id="ci-child",
        normalized_signature="sig",
        workload_fingerprint="wf",
        policy_fingerprint="pf",
        expected_seconds=0.05,
        soft_seconds=0.1,
        stall_seconds=None,
        hard_seconds=1.0,
        diagnostic_hard_seconds=1.0,
        termination_grace_seconds=0.2,
        progress_contract_id="pytest-node-transition",
        termination_policy_id="owned-process-group",
        prediction_source="registry-default",
        confidence="none",
        sample_count=0,
        admission_decision="run",
        context_signature="test",
    )
    result = run_owned_command(
        spam_command(0.4, "tests/demo.py::test_demo PASSED"),
        cwd=ROOT,
        env=None,
        hard_seconds=plan.hard_seconds,
        soft_seconds=plan.soft_seconds,
        stall_seconds=plan.stall_seconds,
        termination_grace_seconds=plan.termination_grace_seconds,
        tracker=None,
        enforce_hard=True,
        enforce_stall=False,
        soft_report_plan=plan,
        active_child="focused:pytest",
    )
    captured = capsys.readouterr().out
    assert "EXECUTION_STATE=running-over-soft" in captured
    assert result.exit_code == 0
    assert result.duration_seconds > plan.soft_seconds
