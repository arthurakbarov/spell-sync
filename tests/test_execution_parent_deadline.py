"""Parent hard deadline enforcement tests."""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.gate_controller import GateController  # noqa: E402
from scripts.execution_control.models import ExecutionStatus  # noqa: E402
from scripts.execution_control.process_tree import run_owned_command  # noqa: E402
from tests.conftest_execution import sleep_command  # noqa: E402


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


def test_parent_hard_deadline_stops_long_child(gate_controller, history, monkeypatch):
    original_run = gate_controller.run

    def _fast_grace_run(plan, command, **kwargs):
        plan = replace(
            plan,
            termination_grace_seconds=0.15,
            diagnostic_hard_seconds=0.05,
        )
        return original_run(plan, command, **kwargs)

    monkeypatch.setattr(gate_controller, "run", _fast_grace_run)
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
    gate.parent_plan = replace(gate.parent_plan, hard_seconds=0.1)
    gate.parent_hard_deadline = time.monotonic() + 0.1
    started = time.monotonic()
    rc, _ = gate_controller.run_child(
        gate,
        child_execution_id="ci:pytest",
        command=sleep_command(0.5),
        mode="full-ci",
        required=True,
    )
    elapsed = time.monotonic() - started
    assert rc == 124
    assert elapsed < 1.25
    parent = gate_controller.finish_gate(gate, exit_code=rc)
    assert parent["result"] == ExecutionStatus.TIMEOUT_HARD.value
    with history._connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) AS c FROM spans WHERE execution_id = ?",
            ("gate:full-ci",),
        ).fetchone()["c"]
    assert count == 1


def test_parent_deadline_propagation_in_owned_command(isolated_state_dir):
    del isolated_state_dir
    started = time.monotonic()
    result = run_owned_command(
        sleep_command(0.5),
        cwd=ROOT,
        env=None,
        hard_seconds=2.0,
        soft_seconds=1.0,
        stall_seconds=None,
        termination_grace_seconds=0.15,
        tracker=None,
        enforce_hard=True,
        parent_deadline_monotonic=time.monotonic() + 0.1,
    )
    elapsed = time.monotonic() - started
    assert result.timed_out is True
    assert result.exit_code == 124
    assert elapsed < 0.75
