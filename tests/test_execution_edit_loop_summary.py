"""Edit-loop summary fields are present in budget reports."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.budget_report import build_execution_budget_report  # noqa: E402
from scripts.execution_control.history import HistoryStore  # noqa: E402
from scripts.execution_control.models import SpanRecord  # noqa: E402
from scripts.execution_control.session import SessionTotals, build_edit_loop_summary  # noqa: E402


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


def _span(**overrides: object) -> SpanRecord:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    base: dict[str, object] = dict(
        run_id="run-summary",
        span_id="span-1",
        parent_span_id=None,
        execution_id="gate:focused-module",
        profile_id="focused-module",
        normalized_signature="sig",
        workload_fingerprint="wf",
        policy_fingerprint="pf",
        start_time=now,
        end_time=now,
        duration_seconds=1.0,
        exit_code=0,
        status="success",
        expected_seconds=60.0,
        soft_seconds=120.0,
        stall_seconds=None,
        hard_seconds=300.0,
        prediction_source="registry-default",
        confidence="none",
        sample_count=0,
        progress_event_count=1,
        maximum_progress_gap=0.1,
        active_child_at_end=None,
        accepted_for_learning=True,
        quarantine_reason=None,
        diagnostic_bundle=None,
        environment_signature="",
    )
    base.update(overrides)
    return SpanRecord(**base)  # type: ignore[arg-type]


def test_edit_loop_summary_counters_from_history(isolated_state_dir, history: HistoryStore) -> None:
    del isolated_state_dir
    history.insert_span(_span(span_id="s1", execution_id="gate:focused-module"), context_signature="ctx")
    history.insert_span(
        _span(span_id="s2", run_id="run-2", execution_id="gate:pre-final", profile_id="pre-final"),
        context_signature="ctx",
    )
    history.insert_span(
        _span(span_id="s3", run_id="run-3", execution_id="gate:full-ci", profile_id="full-ci"),
        context_signature="ctx",
    )
    history.insert_span(
        _span(span_id="s4", run_id="run-4", status="reused", exit_code=0),
        context_signature="ctx",
    )
    history.insert_span(
        _span(
            span_id="s5",
            run_id="run-5",
            status="defer-to-pre-final",
            exit_code=1,
        ),
        context_signature="ctx",
    )
    summary = build_edit_loop_summary(SessionTotals(edit_seconds=10.0), history=history)
    assert summary["focusedRunCount"] == 2  # focused-module success + reused parent
    assert summary["preFinalRunCount"] == 1
    assert summary["fullCiRunCount"] == 1
    assert summary["evidenceReuses"] == 1
    assert summary["plansDeferred"] == 1
