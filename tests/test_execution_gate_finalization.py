"""Exactly-once parent gate finalization tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.gate_controller import GateController  # noqa: E402
from scripts.execution_control.models import ExecutionStatus  # noqa: E402
from scripts.execution_control.session import load_session  # noqa: E402
from tests.conftest_execution import exit_command  # noqa: E402


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


def test_child_failure_creates_one_parent_span_and_session(gate_controller, history):
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
    totals_before, _, _ = load_session()
    rc, _ = gate_controller.run_child(
        gate,
        child_execution_id="pre-final:pytest",
        command=exit_command(3),
        mode="pre-final",
        required=True,
    )
    assert rc == 3
    assert gate.stopped is True
    parent = gate_controller.finish_gate(gate, exit_code=rc)
    duplicate = gate_controller.finish_gate(gate, exit_code=rc)
    assert duplicate == parent
    with history._connect() as connection:
        rows = connection.execute(
            "SELECT status FROM spans WHERE execution_id = ?",
            ("gate:pre-final",),
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] in {ExecutionStatus.FAILED.value, "failed"}
    assert history.degraded is False
    totals_after, _, _ = load_session()
    assert totals_after.pre_final_seconds >= totals_before.pre_final_seconds
