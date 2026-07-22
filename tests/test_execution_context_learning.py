"""Exact context learning tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.context import build_context  # noqa: E402
from scripts.execution_control.controller import ExecutionController  # noqa: E402
from scripts.execution_control.history import HistoryStore  # noqa: E402
from scripts.execution_control.prediction import predict_thresholds  # noqa: E402
from tests.conftest_execution import sleep_command  # noqa: E402


def _fake_necessity(result: str = "full-required"):
    return SimpleNamespace(
        assess_ci_necessity=lambda _root: SimpleNamespace(
            result=result,
            reusable_run_head="",
        )
    )


def test_successful_child_stores_exact_context_and_learns(registry, isolated_state_dir):
    del isolated_state_dir
    history = HistoryStore.open()
    controller = ExecutionController(root=ROOT, registry=registry, history=history)
    context = build_context(execution_mode="full-ci", coverage=True)
    with patch(
        "scripts.execution_control.admission._load_ci_necessity",
        return_value=_fake_necessity(),
    ):
        plan, state = controller.prepare_plan(
            execution_id="ci:pytest",
            command=sleep_command(0.05),
            mode="full-ci",
            required=True,
            coverage=True,
        )
    assert plan is not None and state == "run"
    assert plan.context_signature == context.signature()
    execution = controller.run(plan, sleep_command(0.05), cwd=ROOT, active_child="ci:pytest")
    assert execution.exit_code == 0

    exact = history.fetch_learning_durations(
        execution_id="ci:pytest",
        workload_fingerprint=plan.workload_fingerprint,
        context_signature=plan.context_signature,
    )
    assert len(exact) == 1

    prediction = predict_thresholds(
        profile=registry.profiles["ci-child"],
        registry=registry,
        history=history,
        execution_id="ci:pytest",
        workload_fingerprint_value=plan.workload_fingerprint,
        context=build_context(execution_mode="full-ci", coverage=True),
    )
    assert prediction.prediction_source == "exact-history"
    assert prediction.sample_count == 1
