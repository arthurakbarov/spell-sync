"""Planner supervision prevents downstream children after planner failure."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.gate_controller import GateController  # noqa: E402
from scripts.execution_control.gate_previews import (  # noqa: E402
    open_gate_after_previews,
    preview_focused_child_plans,
    run_bounded_planner,
)
from scripts.execution_control.history import HistoryStore  # noqa: E402
from scripts.execution_control.process_tree import ProcessResult  # noqa: E402
from tests.conftest_execution import echo_command  # noqa: E402


@pytest.fixture
def gate_controller(registry, history, isolated_state_dir):
    del isolated_state_dir
    return GateController(root=ROOT, registry=registry, history=history)


def _timeout_result() -> ProcessResult:
    return ProcessResult(
        exit_code=124,
        duration_seconds=60.0,
        timed_out=True,
        timeout_kind="hard",
        stdout_tail="",
        stderr_tail="",
        progress_event_count=0,
        maximum_progress_gap=0.0,
        start_time_iso="2026-01-01T00:00:00Z",
        end_time_iso="2026-01-01T00:01:00Z",
    )


def _planner_command(tmp_path: Path) -> list[str]:
    return [
        "python3",
        str(ROOT / "scripts" / "build_focused_plan.py"),
        "--output",
        str(tmp_path / "plan.json"),
    ]


def _child_execution_ids(history, execution_id: str) -> list[str]:
    with history._connect() as connection:
        rows = connection.execute(
            "SELECT execution_id FROM spans WHERE execution_id = ?",
            (execution_id,),
        ).fetchall()
    return [row["execution_id"] for row in rows]


def test_focused_planner_timeout_blocks_test_subprocesses(gate_controller, history, tmp_path):
    def _run(command, **kwargs):
        if any("build_focused_plan.py" in part for part in command):
            return _timeout_result()
        raise AssertionError(f"unexpected child command after planner timeout: {command}")

    with patch("scripts.execution_control.controller.run_owned_command", side_effect=_run):
        rc, state = run_bounded_planner(
            gate_controller,
            planner_execution_id="focused:planner",
            command=_planner_command(tmp_path),
            mode="cluster",
        )
    assert rc == 124
    assert state == "run"
    assert _child_execution_ids(history, "focused:pytest") == []


def test_pre_final_planner_timeout_blocks_checks(gate_controller, history, tmp_path):
    def _run(command, **kwargs):
        if any("build_pre_final_plan.py" in part for part in command):
            return _timeout_result()
        raise AssertionError(f"unexpected child command after planner timeout: {command}")

    with patch("scripts.execution_control.controller.run_owned_command", side_effect=_run):
        rc, state = run_bounded_planner(
            gate_controller,
            planner_execution_id="pre-final:planner",
            command=[
                "python3",
                str(ROOT / "scripts" / "build_pre_final_plan.py"),
                "--output",
                str(tmp_path / "plan.json"),
            ],
            mode="pre-final",
        )
    assert rc == 124
    assert _child_execution_ids(history, "pre-final:validators") == []


def test_focused_runner_uses_planner_before_gate(isolated_state_dir, registry, tmp_path):
    del isolated_state_dir
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "plan": {"validators": [], "pytest_targets": [], "command": []},
                "steps": [{"kind": "validator", "argv": echo_command("step")}],
                "metadata": [],
                "runKey": "test",
                "testFileCount": 0,
            }
        ),
        encoding="utf-8",
    )
    gate_controller = GateController(
        root=ROOT,
        registry=registry,
        history=HistoryStore.open(),
        enforce_hard=True,
        enforce_stall=False,
    )
    calls: list[str] = []

    def _run(command, **kwargs):
        joined = " ".join(command)
        calls.append(joined)
        if "build_focused_plan.py" in joined:
            plan_path.write_text(
                json.dumps(
                    {
                        "plan": {"validators": [], "pytest_targets": [], "command": []},
                        "steps": [{"kind": "validator", "argv": echo_command("step")}],
                        "metadata": [],
                        "runKey": "test",
                        "testFileCount": 0,
                    }
                ),
                encoding="utf-8",
            )
            return ProcessResult(
                exit_code=0,
                duration_seconds=0.1,
                timed_out=False,
                timeout_kind=None,
                stdout_tail="",
                stderr_tail="",
                progress_event_count=0,
                maximum_progress_gap=0.0,
                start_time_iso="2026-01-01T00:00:00Z",
                end_time_iso="2026-01-01T00:00:00Z",
            )
        return ProcessResult(
            exit_code=0,
            duration_seconds=0.1,
            timed_out=False,
            timeout_kind=None,
            stdout_tail="",
            stderr_tail="",
            progress_event_count=0,
            maximum_progress_gap=0.0,
            start_time_iso="2026-01-01T00:00:00Z",
            end_time_iso="2026-01-01T00:00:01Z",
        )

    with patch("scripts.execution_control.controller.run_owned_command", side_effect=_run):
        planner_rc, _ = run_bounded_planner(
            gate_controller,
            planner_execution_id="focused:planner",
            command=_planner_command(plan_path),
            mode="cluster",
        )
        assert planner_rc == 0
        child_plans = preview_focused_child_plans(
            ROOT,
            registry,
            steps=(("validator", echo_command("step")),),
            mode="cluster",
        )
        gate, state, _, _ = open_gate_after_previews(
            gate_controller,
            execution_id="gate:focused-cluster",
            command=["python3", "scripts/run_focused_tests.py"],
            mode="cluster",
            child_plans=child_plans,
            required=False,
        )
        assert gate is not None and state == "run"
        gate_controller.run_child_with_plan(
            gate,
            child_plans[0],
            command=echo_command("step"),
        )
    assert any("build_focused_plan.py" in call for call in calls)
    gate_controller.finish_gate(gate, exit_code=0)
