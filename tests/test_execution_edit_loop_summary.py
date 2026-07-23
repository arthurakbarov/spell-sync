"""Edit-loop summary fields are present in budget reports."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.budget_report import build_execution_budget_report  # noqa: E402


def test_edit_loop_summary_fields() -> None:
    payload = build_execution_budget_report(ROOT, edit_loop=True)
    summary = payload["editLoopSummary"]
    for key in (
        "sessionCount",
        "focusedRunCount",
        "estimatedSecondsAvoided",
        "medianFocusedCycleSeconds",
        "plansNarrowed",
        "evidenceReuses",
    ):
        assert key in summary
