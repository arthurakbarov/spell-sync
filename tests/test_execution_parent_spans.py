"""Parent gate span linkage tests."""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.gate_controller import GateController  # noqa: E402
from tests.conftest_execution import echo_command, sleep_command  # noqa: E402


def _fake_necessity(result: str = "full-required"):
    return SimpleNamespace(
        assess_ci_necessity=lambda _root: SimpleNamespace(
            result=result,
            reusable_run_head="",
        )
    )


@pytest.fixture
def gate_controller(registry, history, isolated_state_dir):
    del isolated_state_dir
    return GateController(root=ROOT, registry=registry, history=history)


def test_parent_gate_records_wall_duration_not_child_sum(gate_controller, history):
    with patch(
        "scripts.execution_control.admission._load_ci_necessity",
        return_value=_fake_necessity(),
    ):
        gate, state = gate_controller.begin_gate(
            execution_id="gate:full-ci",
            command=["python3", "scripts/ci_runner.py"],
            mode="full-ci",
            required=True,
        )
    assert gate is not None and state == "run"
    time.sleep(0.05)
    rc, _ = gate_controller.run_child(
        gate,
        child_execution_id="ci:execution-budget-registry",
        command=echo_command("child"),
        mode="full-ci",
        required=True,
    )
    assert rc == 0
    timing = gate_controller.finish_gate(gate, exit_code=0)
    assert timing["actualSeconds"] >= 0.05
    assert float(timing["childDurationSum"]) < float(timing["actualSeconds"])
    rows = history.fetch_profile_durations(execution_id="gate:full-ci", limit=1)
    assert rows
    assert rows[0] == pytest.approx(float(timing["actualSeconds"]), rel=0.2)


def test_child_span_links_parent_run_and_span(gate_controller, history):
    with patch(
        "scripts.execution_control.admission._load_ci_necessity",
        return_value=_fake_necessity(),
    ):
        gate, _ = gate_controller.begin_gate(
            execution_id="gate:pre-final",
            command=["python3", "scripts/run_pre_final_checks.py"],
            mode="pre-final",
            required=True,
        )
    assert gate is not None
    rc, child_execution = gate_controller.run_child(
        gate,
        child_execution_id="pre-final:pytest",
        command=sleep_command(0.05),
        mode="pre-final",
        required=True,
    )
    assert rc == 0
    assert child_execution is not None
    child_timing = child_execution.timing
    assert child_timing.get("parentSpanId") == gate.parent_span_id
    with history._connect() as connection:
        row = connection.execute(
            "SELECT run_id, parent_span_id FROM spans WHERE execution_id = ? ORDER BY start_time DESC LIMIT 1",
            ("pre-final:pytest",),
        ).fetchone()
    assert row is not None
    assert row["run_id"] == gate.parent_plan.run_id
    assert row["parent_span_id"] == gate.parent_span_id
    gate_controller.finish_gate(gate, exit_code=0)


def test_child_timeout_stops_gate(gate_controller, monkeypatch):
    from scripts.execution_control.process_tree import ProcessResult

    def _timeout(*args, **kwargs):
        return ProcessResult(
            exit_code=124,
            duration_seconds=1.0,
            timed_out=True,
            timeout_kind="hard",
            stdout_tail="",
            stderr_tail="",
            progress_event_count=0,
            maximum_progress_gap=0.0,
            start_time_iso="2026-01-01T00:00:00Z",
            end_time_iso="2026-01-01T00:00:01Z",
        )

    monkeypatch.setattr("scripts.execution_control.controller.run_owned_command", _timeout)
    with patch(
        "scripts.execution_control.admission._load_ci_necessity",
        return_value=_fake_necessity(),
    ):
        gate, _ = gate_controller.begin_gate(
            execution_id="gate:full-ci",
            command=["python3", "scripts/ci_runner.py"],
            mode="full-ci",
            required=True,
        )
    assert gate is not None
    rc, _ = gate_controller.run_child(
        gate,
        child_execution_id="ci:pytest",
        command=["sleep", "30"],
        mode="full-ci",
        required=True,
    )
    assert rc == 124
    assert gate.stopped is True
    parent = gate_controller.finish_gate(gate, exit_code=rc)
    assert parent["result"] in {"failed", "timeout-hard"}
