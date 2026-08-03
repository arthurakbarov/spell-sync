"""Prediction accuracy metrics expose MAE/MAPE with confidence gating."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.budget_analysis import build_execution_budget_report  # noqa: E402


def test_prediction_metrics_shape() -> None:
    payload = build_execution_budget_report(ROOT)
    for item in payload["executionIds"]:
        assert "meanAbsoluteErrorSeconds" in item
        assert "meanAbsolutePercentageError" in item
        assert "confidence" in item
