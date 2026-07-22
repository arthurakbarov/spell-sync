"""Duration prediction formula tests."""

from __future__ import annotations

from datetime import datetime, timezone

from scripts.execution_control.context import build_context
from scripts.execution_control.models import SpanRecord
from scripts.execution_control.prediction import predict_thresholds


def _insert_success(
    history, *, execution_id: str, workload_fp: str, duration: float, context_sig: str
):
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    record = SpanRecord(
        run_id=history.new_run_id(),
        span_id=history.new_span_id(),
        parent_span_id=None,
        execution_id=execution_id,
        profile_id="ci-child",
        normalized_signature="sig",
        workload_fingerprint=workload_fp,
        policy_fingerprint="pf",
        start_time=now,
        end_time=now,
        duration_seconds=duration,
        exit_code=0,
        status="success",
        expected_seconds=60.0,
        soft_seconds=120.0,
        stall_seconds=None,
        hard_seconds=300.0,
        prediction_source="registry-default",
        confidence="none",
        sample_count=0,
        progress_event_count=0,
        maximum_progress_gap=0.0,
        active_child_at_end=None,
        accepted_for_learning=True,
        quarantine_reason=None,
        diagnostic_bundle=None,
    )
    history.insert_span(record, context_signature=context_sig)


def test_cold_start_uses_registry_default(registry, history):
    profile = registry.profiles["focused-module"]
    context = build_context(execution_mode="exact")
    result = predict_thresholds(
        profile=profile,
        registry=registry,
        history=history,
        execution_id=profile.execution_id,
        workload_fingerprint_value="cold-workload-fingerprint",
        context=context,
    )
    assert result.prediction_source == "registry-default"
    assert result.confidence == "none"
    assert result.sample_count == 0


def test_exact_history_used_when_available(registry, history):
    profile = registry.profiles["focused-module"]
    context = build_context(execution_mode="exact", test_file_count=1)
    workload_fp = "exact-workload-fp"
    for duration in (12.0, 14.0, 13.0):
        _insert_success(
            history,
            execution_id=profile.execution_id,
            workload_fp=workload_fp,
            duration=duration,
            context_sig=context.signature(),
        )
    result = predict_thresholds(
        profile=profile,
        registry=registry,
        history=history,
        execution_id=profile.execution_id,
        workload_fingerprint_value=workload_fp,
        context=context,
    )
    assert result.prediction_source == "exact-history"
    assert result.sample_count == 3
    assert result.confidence == "low"


def test_workload_history_fallback_without_context_match(registry, history):
    profile = registry.profiles["focused-module"]
    context = build_context(execution_mode="exact", test_file_count=1)
    workload_fp = "workload-only-fp"
    other_context = build_context(execution_mode="cluster", test_file_count=50)
    _insert_success(
        history,
        execution_id=profile.execution_id,
        workload_fp=workload_fp,
        duration=25.0,
        context_sig=other_context.signature(),
    )
    result = predict_thresholds(
        profile=profile,
        registry=registry,
        history=history,
        execution_id=profile.execution_id,
        workload_fingerprint_value=workload_fp,
        context=context,
    )
    assert result.prediction_source == "workload-history"
    assert result.sample_count == 1


def test_profile_history_fallback(registry, history):
    profile = registry.profiles["focused-module"]
    context = build_context(execution_mode="exact")
    _insert_success(
        history,
        execution_id=profile.execution_id,
        workload_fp="other-workload",
        duration=30.0,
        context_sig=context.signature(),
    )
    result = predict_thresholds(
        profile=profile,
        registry=registry,
        history=history,
        execution_id=profile.execution_id,
        workload_fingerprint_value="brand-new-workload",
        context=context,
    )
    assert result.prediction_source == "profile-history"
    assert result.sample_count == 1


def test_low_sample_blend_between_initial_and_learned(registry, history):
    profile = registry.profiles["focused-module"]
    context = build_context(execution_mode="exact")
    workload_fp = "blend-workload"
    for duration in (10.0, 10.0, 10.0):
        _insert_success(
            history,
            execution_id=profile.execution_id,
            workload_fp=workload_fp,
            duration=duration,
            context_sig=context.signature(),
        )
    result = predict_thresholds(
        profile=profile,
        registry=registry,
        history=history,
        execution_id=profile.execution_id,
        workload_fingerprint_value=workload_fp,
        context=context,
    )
    assert result.expected_seconds < profile.initial_expected_seconds
    assert result.expected_seconds >= 10.0
    assert result.sample_count == 3


def test_stall_seconds_for_contract_profile(registry, history):
    profile = registry.profiles["ci-child"]
    context = build_context(execution_mode="cluster", test_node_count=5)
    result = predict_thresholds(
        profile=profile,
        registry=registry,
        history=history,
        execution_id="ci:pytest",
        workload_fingerprint_value="stall-workload",
        context=context,
    )
    assert result.stall_seconds is not None
    assert profile.stall_floor_seconds <= result.stall_seconds <= profile.stall_cap_seconds
