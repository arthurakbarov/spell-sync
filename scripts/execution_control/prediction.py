"""Duration prediction from history and registry defaults."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .history import HistoryStore
from .models import ExecutionPlan, NormalizedContext
from .registry import ExecutionBudgetRegistry, Profile
from .statistics import compute_stats, confidence_label


def _round_up_seconds(value: float, step: float = 5.0) -> float:
    return math.ceil(value / step) * step


@dataclass(frozen=True, slots=True)
class PredictionResult:
    expected_seconds: float
    soft_seconds: float
    stall_seconds: float | None
    hard_seconds: float
    prediction_source: str
    confidence: str
    sample_count: int


def _blend_expected(initial: float, learned: float, sample_count: int) -> float:
    weight = min(1.0, sample_count / 10.0)
    if sample_count >= 10:
        return _round_up_seconds(learned)
    blended = initial * (1.0 - weight) + learned * weight
    return _round_up_seconds(blended)


def predict_thresholds(
    *,
    profile: Profile,
    registry: ExecutionBudgetRegistry,
    history: HistoryStore,
    execution_id: str,
    workload_fingerprint_value: str,
    context: NormalizedContext,
) -> PredictionResult:
    exact = history.fetch_learning_durations(
        execution_id=execution_id,
        workload_fingerprint=workload_fingerprint_value,
        context_signature=context.signature(),
    )
    source = "registry-default"
    durations = exact
    if exact:
        source = "exact-history"
    else:
        bucket = history.fetch_learning_durations(
            execution_id=execution_id,
            workload_fingerprint=workload_fingerprint_value,
            context_signature=None,
        )
        if bucket:
            durations = bucket
            source = "workload-history"
        else:
            profile_hist = history.fetch_profile_durations(execution_id=execution_id)
            if profile_hist:
                durations = profile_hist
                source = "profile-history"

    stats = compute_stats(durations)
    sample_count = stats.sample_count
    if sample_count:
        expected = _blend_expected(
            profile.initial_expected_seconds,
            stats.median,
            sample_count,
        )
    else:
        expected = _round_up_seconds(profile.initial_expected_seconds)
        source = "registry-default"

    soft_candidates = [
        profile.initial_soft_seconds,
        expected * 1.5,
    ]
    if stats.sample_count:
        soft_candidates.append(stats.p90 + 2 * stats.robust_sigma)
    soft = _round_up_seconds(max(soft_candidates))

    stall_seconds: float | None = None
    if profile.progress_contract:
        stall_seconds = min(
            profile.stall_cap_seconds,
            max(
                profile.stall_floor_seconds,
                stats.max_progress_gap * 2 or profile.stall_floor_seconds,
            ),
        )

    hard_candidates = [
        profile.initial_hard_seconds,
        soft * 1.5,
        soft + profile.termination_grace_seconds,
    ]
    if stats.p95 is not None:
        hard_candidates.append(stats.p95 * 1.75)
    hard = min(profile.hard_cap_seconds, registry.global_hard_cap_seconds)
    hard = min(hard, _round_up_seconds(max(hard_candidates)))

    return PredictionResult(
        expected_seconds=expected,
        soft_seconds=soft,
        stall_seconds=stall_seconds,
        hard_seconds=hard,
        prediction_source=source,
        confidence=confidence_label(sample_count),
        sample_count=sample_count,
    )


def build_execution_plan(
    *,
    run_id: str,
    execution_id: str,
    profile: Profile,
    registry: ExecutionBudgetRegistry,
    history: HistoryStore,
    workload_fingerprint_value: str,
    policy_fingerprint_value: str,
    normalized_signature_value: str,
    context: NormalizedContext,
    admission_decision: str,
) -> ExecutionPlan:
    prediction = predict_thresholds(
        profile=profile,
        registry=registry,
        history=history,
        execution_id=execution_id,
        workload_fingerprint_value=workload_fingerprint_value,
        context=context,
    )
    return ExecutionPlan(
        run_id=run_id,
        execution_id=execution_id,
        profile_id=profile.profile_id,
        normalized_signature=normalized_signature_value,
        workload_fingerprint=workload_fingerprint_value,
        policy_fingerprint=policy_fingerprint_value,
        expected_seconds=prediction.expected_seconds,
        soft_seconds=prediction.soft_seconds,
        stall_seconds=prediction.stall_seconds,
        hard_seconds=prediction.hard_seconds,
        diagnostic_hard_seconds=profile.diagnostic_hard_seconds,
        termination_grace_seconds=profile.termination_grace_seconds,
        progress_contract_id=profile.progress_contract or None,
        termination_policy_id="owned-process-group",
        prediction_source=prediction.prediction_source,
        confidence=prediction.confidence,
        sample_count=prediction.sample_count,
        admission_decision=admission_decision,
        context_signature=context.signature(),
    )
