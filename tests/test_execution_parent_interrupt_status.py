"""Parent interrupt lifecycle across all gate classes."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.gate_controller import GateController  # noqa: E402
from scripts.execution_control.models import ExecutionStatus  # noqa: E402


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


def _assert_interrupt_spans(history, *, parent_id: str, child_id: str) -> None:
    with history._connect() as connection:
        parent = connection.execute(
            "SELECT status, exit_code FROM spans WHERE execution_id = ? "
            "ORDER BY start_time DESC LIMIT 1",
            (parent_id,),
        ).fetchone()
        child = connection.execute(
            "SELECT status, exit_code FROM spans WHERE execution_id = ? "
            "ORDER BY start_time DESC LIMIT 1",
            (child_id,),
        ).fetchone()
        success_parent = connection.execute(
            "SELECT COUNT(*) AS count FROM spans WHERE execution_id = ? AND status = 'success'",
            (parent_id,),
        ).fetchone()
        leases = connection.execute("SELECT COUNT(*) AS count FROM active_leases").fetchone()
    assert parent is not None
    assert child is not None
    assert parent["status"] == ExecutionStatus.INTERRUPTED.value
    assert parent["exit_code"] == 130
    assert child["status"] == ExecutionStatus.INTERRUPTED.value
    assert child["exit_code"] == 130
    assert success_parent["count"] == 0
    assert leases["count"] == 0


@pytest.mark.parametrize(
    ("parent_id", "child_id", "mode"),
    [
        ("gate:focused-cluster", "focused:pytest", "cluster"),
        ("gate:pre-final", "pre-final:validators", "pre-final"),
        ("gate:snapshot-tests", "snapshot-tests:pytest", "snapshot-tests"),
    ],
)
def test_gate_parent_interrupt_lifecycle(
    gate_controller,
    history,
    parent_id,
    child_id,
    mode,
):
    gate, state = gate_controller.begin_gate(
        execution_id=parent_id,
        command=["python3", "scripts/runner.py"],
        mode=mode,
        required=False,
    )
    assert gate is not None and state == "run"
    with patch(
        "scripts.execution_control.controller.run_owned_command",
        side_effect=KeyboardInterrupt,
    ):
        with pytest.raises(KeyboardInterrupt):
            gate_controller.run_child(
                gate,
                child_execution_id=child_id,
                command=["python3", "-c", "print('child')"],
                mode=mode,
                required=False,
            )
    gate_controller.finish_gate(
        gate,
        exit_code=130,
        status=ExecutionStatus.INTERRUPTED,
    )
    _assert_interrupt_spans(history, parent_id=parent_id, child_id=child_id)


def test_full_ci_gate_parent_interrupt_lifecycle(gate_controller, history):
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
    with patch(
        "scripts.execution_control.controller.run_owned_command",
        side_effect=KeyboardInterrupt,
    ):
        with pytest.raises(KeyboardInterrupt):
            gate_controller.run_child(
                gate,
                child_execution_id="ci:docs-style",
                command=["python3", "-c", "print('child')"],
                mode="full-ci",
                required=True,
            )
    gate_controller.finish_gate(
        gate,
        exit_code=130,
        status=ExecutionStatus.INTERRUPTED,
    )
    _assert_interrupt_spans(
        history,
        parent_id="gate:full-ci",
        child_id="ci:docs-style",
    )
