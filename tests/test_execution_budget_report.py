"""Execution budget report exposes edit-loop and prediction metrics."""

from __future__ import annotations

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.budget_report import (  # noqa: E402
    REPORT_SCHEMA_VERSION,
    build_execution_budget_report,
    render_text_report,
)
from scripts.execution_control.statistics import compute_mae, compute_mape  # noqa: E402


def test_report_schema_version() -> None:
    payload = build_execution_budget_report(ROOT, edit_loop=True)
    assert payload["schemaVersion"] == REPORT_SCHEMA_VERSION
    assert "editLoopSummary" in payload


def test_insufficient_data_confidence() -> None:
    payload = build_execution_budget_report(ROOT, execution_id="tests.core")
    ids = payload["executionIds"]
    if ids:
        assert ids[0]["confidence"] in {"insufficient-data", "none", "very-low", "low", "medium", "high"}


def test_mae_mape_helpers() -> None:
    assert compute_mae([10.0, 20.0], [12.0, 18.0]) == 2.0
    assert compute_mape([10.0, 20.0], [12.0, 18.0]) == pytest.approx(0.15)


def test_text_report_renders() -> None:
    payload = build_execution_budget_report(ROOT, edit_loop=True)
    text = render_text_report(payload)
    assert "EXECUTION_BUDGET_REPORT=success" in text
