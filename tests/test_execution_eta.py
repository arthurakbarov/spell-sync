"""ETA announce and interactive allowance unit tests."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from scripts.execution_control.eta import (
    PROMPT_ALLOWANCE_SECONDS,
    announce_expected_eta,
    announce_plan_eta,
    compute_announcement,
    format_announcement,
    format_eta_seconds,
)
from scripts.execution_control.interactive import (
    capture_waiting,
    current_waiting_seconds,
    interactive_allowance_seconds,
    prompt_user,
)
from scripts.execution_control.models import ExecutionPlan
from scripts.execution_control.observe import record_observation

ROOT = Path(__file__).resolve().parents[1]


def _plan(
    *,
    expected: float,
    execution_id: str = "gate:focused-module",
    prompts: int = 0,
) -> ExecutionPlan:
    return ExecutionPlan(
        run_id="eta-run",
        execution_id=execution_id,
        profile_id="focused-module",
        normalized_signature="sig",
        workload_fingerprint="wf",
        policy_fingerprint="pf",
        expected_seconds=expected,
        soft_seconds=expected * 2,
        stall_seconds=None,
        hard_seconds=expected * 4,
        diagnostic_hard_seconds=10.0,
        termination_grace_seconds=1.0,
        progress_contract_id=None,
        termination_policy_id="owned-process-group",
        prediction_source="test",
        confidence="none",
        sample_count=0,
        admission_decision="run",
        context_signature="test",
        expected_prompt_count=prompts,
    )


def test_format_eta_seconds():
    assert format_eta_seconds(4) == "4s"
    assert format_eta_seconds(125) == "2m05s"


def test_short_plan_is_silent(isolated_state_dir):
    del isolated_state_dir
    assert (
        compute_announcement(
            _plan(expected=3.0, execution_id="gate:test-eta-short"),
            root=ROOT,
            history=None,
        )
        is None
    )


def test_long_plan_announces(isolated_state_dir):
    del isolated_state_dir
    ann = compute_announcement(
        _plan(expected=12.0, execution_id="gate:test-eta-long"),
        root=ROOT,
        history=None,
    )
    assert ann is not None
    assert ann.should_announce
    assert "eta: expected ~12s" in format_announcement(ann)


def test_interactive_prompts_added_to_display_not_work_budget(isolated_state_dir):
    del isolated_state_dir
    plan = _plan(expected=3.0, execution_id="gate:test-eta-prompt", prompts=2)
    assert plan.hard_seconds == 12.0
    assert plan.interactive_allowance_seconds == 2 * PROMPT_ALLOWANCE_SECONDS
    assert plan.wall_hard_seconds == plan.hard_seconds + 10.0
    ann = compute_announcement(plan, root=ROOT, history=None)
    assert ann is not None
    assert ann.work_seconds == 3.0
    assert ann.display_seconds == 13.0
    text = format_announcement(ann)
    assert "interactive ×2" in text


def test_announce_respects_disable_env(isolated_state_dir, monkeypatch):
    del isolated_state_dir
    monkeypatch.setenv("SPELL_SYNC_ETA_ANNOUNCE", "0")
    stream = StringIO()
    result = announce_plan_eta(_plan(expected=90.0), root=ROOT, history=None, stream=stream)
    assert result is None
    assert stream.getvalue() == ""


def test_announce_expected_eta_standalone(isolated_state_dir):
    del isolated_state_dir
    stream = StringIO()
    ann = announce_expected_eta(
        "gate:test-eta-standalone",
        work_seconds=40.0,
        prompt_count=1,
        root=ROOT,
        history=None,
        stream=stream,
    )
    assert ann is not None
    assert "eta: expected ~45s" in stream.getvalue()


def test_prompt_user_records_waiting_outside_work(isolated_state_dir):
    del isolated_state_dir
    with capture_waiting():
        reply = prompt_user(
            "continue?",
            stream_in=StringIO("yes\n"),
            stream_out=StringIO(),
        )
        assert reply == "yes"
        assert current_waiting_seconds() >= 0.0
    assert interactive_allowance_seconds(3) == 15.0


def test_record_observation_updates_history(isolated_state_dir):
    del isolated_state_dir
    from scripts.execution_control.history import HistoryStore

    store = HistoryStore.open()
    try:
        accepted = record_observation(
            execution_id="dev-loop:L0-test",
            duration_seconds=12.0,
            exit_code=0,
            expected_seconds=60.0,
            soft_seconds=60.0,
            history=store,
        )
        assert accepted is True
        samples = store.fetch_profile_durations(execution_id="dev-loop:L0-test", limit=5)
        assert samples == [12.0]
    finally:
        store.close()
