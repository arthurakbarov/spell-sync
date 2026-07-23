"""Robust duration statistics."""

from __future__ import annotations

import statistics
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DurationStats:
    sample_count: int
    median: float
    p75: float
    p90: float
    p95: float | None
    mad: float
    robust_sigma: float
    max_progress_gap: float


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    index = (len(ordered) - 1) * pct
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def compute_stats(
    durations: list[float],
    *,
    progress_gaps: list[float] | None = None,
) -> DurationStats:
    if not durations:
        return DurationStats(
            sample_count=0,
            median=0.0,
            p75=0.0,
            p90=0.0,
            p95=None,
            mad=0.0,
            robust_sigma=0.0,
            max_progress_gap=0.0,
        )
    median = statistics.median(durations)
    deviations = [abs(value - median) for value in durations]
    mad = statistics.median(deviations) if deviations else 0.0
    p95 = _percentile(durations, 0.95) if len(durations) >= 10 else None
    gaps = progress_gaps or []
    return DurationStats(
        sample_count=len(durations),
        median=float(median),
        p75=_percentile(durations, 0.75),
        p90=_percentile(durations, 0.90),
        p95=p95,
        mad=float(mad),
        robust_sigma=float(mad * 1.4826),
        max_progress_gap=max(gaps) if gaps else 0.0,
    )


def confidence_label(sample_count: int) -> str:
    if sample_count <= 0:
        return "none"
    if sample_count <= 2:
        return "very-low"
    if sample_count <= 4:
        return "low"
    if sample_count <= 9:
        return "medium"
    return "high"


def compute_mae(expected: list[float], actual: list[float]) -> float | None:
    if not expected or len(expected) != len(actual):
        return None
    return sum(abs(e - a) for e, a in zip(expected, actual, strict=True)) / len(expected)


def compute_mape(expected: list[float], actual: list[float]) -> float | None:
    if not expected or len(expected) != len(actual):
        return None
    ratios: list[float] = []
    for e, a in zip(expected, actual, strict=True):
        if e <= 0:
            continue
        ratios.append(abs(e - a) / e)
    if not ratios:
        return None
    return sum(ratios) / len(ratios)
