"""Admission NARROW enforcement end-to-end tests."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.admission import assess_admission  # noqa: E402
from scripts.execution_control.controller import ExecutionController  # noqa: E402
from scripts.execution_control.history import HistoryStore  # noqa: E402
from scripts.execution_control.models import AdmissionDecision, ExecutionStatus  # noqa: E402


def _fake_necessity(result: str = "full-required"):
    return SimpleNamespace(
        assess_ci_necessity=lambda _root: SimpleNamespace(
            result=result,
            reusable_run_head="",
        )
    )


def test_narrow_plan_has_narrow_admission_decision(registry, history_store):
    profile = registry.profiles["focused-module"]
    tight_registry = replace(registry, edit_loop_budget_seconds=1.0)
    with patch(
        "scripts.execution_control.admission._load_ci_necessity",
        return_value=_fake_necessity(),
    ):
        plan, execution_plan = assess_admission(
            ROOT,
            execution_id=profile.execution_id,
            profile=profile,
            registry=tight_registry,
            history=history_store,
            command=["python3", "-m", "pytest", "tests/"],
            mode="exact",
            required=False,
        )
    assert plan.decision == AdmissionDecision.NARROW
    assert execution_plan is not None
    assert execution_plan.admission_decision == AdmissionDecision.NARROW.value


def test_edit_loop_budget_exceeded_subprocess_count_zero(isolated_state_dir, registry, monkeypatch):
    del isolated_state_dir
    calls: list[list[str]] = []

    def _fake_popen(command, **kwargs):
        calls.append(list(command))
        raise AssertionError("subprocess must not start under NARROW admission")

    monkeypatch.setattr("subprocess.Popen", _fake_popen)
    tight = replace(registry, edit_loop_budget_seconds=1.0)
    controller = ExecutionController(
        root=ROOT,
        registry=tight,
        history=HistoryStore.open(),
    )
    with patch(
        "scripts.execution_control.admission._load_ci_necessity",
        return_value=_fake_necessity(),
    ):
        plan, state = controller.prepare_plan(
            execution_id="gate:focused-module",
            command=[sys.executable, "-c", "print('blocked')"],
            mode="exact",
            required=False,
            test_file_count=10,
        )
    assert plan is None
    assert state == ExecutionStatus.BLOCKED_ADMISSION.value
    assert calls == []
