"""Unit tests for local minimal wall-budget helpers in run_dev_loop."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_run_dev_loop():
    path = ROOT / "scripts" / "run_dev_loop.py"
    spec = importlib.util.spec_from_file_location("run_dev_loop_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_budget_seconds_match_strict_sla() -> None:
    mod = _load_run_dev_loop()
    assert mod.L0_BUDGET_SECONDS == 60
    assert mod.L1_BUDGET_SECONDS == 120
    assert mod.budget_seconds_for_gate("L0") == 60
    assert mod.budget_seconds_for_gate("L1") == 120


def test_budget_status_within_and_exceeded() -> None:
    mod = _load_run_dev_loop()
    assert mod.budget_status(wall_seconds=59.9, budget_seconds=60) == "within"
    assert mod.budget_status(wall_seconds=60.0, budget_seconds=60) == "within"
    assert mod.budget_status(wall_seconds=60.01, budget_seconds=60) == "exceeded"
