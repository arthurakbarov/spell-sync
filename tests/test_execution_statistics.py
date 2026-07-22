"""Duration statistics tests."""

from __future__ import annotations

from scripts.execution_control.statistics import compute_stats, confidence_label


def test_empty_durations_return_zero_stats():
    stats = compute_stats([])
    assert stats.sample_count == 0
    assert stats.median == 0.0
    assert stats.p95 is None


def test_median_and_percentiles():
    stats = compute_stats([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
    assert stats.median == 5.5
    assert stats.p90 > stats.median
    assert stats.p95 is not None
    assert stats.mad >= 0.0


def test_outlier_robustness():
    stats = compute_stats([1.0, 1.1, 1.2, 1.0, 1.1, 50.0])
    assert stats.median < 2.0
    assert stats.robust_sigma < 10.0


def test_outlier_does_not_dominate_median():
    baseline = [5.0, 5.5, 6.0, 5.8, 6.2, 5.9, 6.1, 5.7]
    with_outlier = baseline + [500.0]
    base_stats = compute_stats(baseline)
    outlier_stats = compute_stats(with_outlier)
    assert abs(outlier_stats.median - base_stats.median) < 1.0


def test_progress_gaps_tracked():
    stats = compute_stats([1.0, 2.0], progress_gaps=[0.5, 3.0, 1.0])
    assert stats.max_progress_gap == 3.0


def test_confidence_buckets():
    assert confidence_label(0) == "none"
    assert confidence_label(2) == "very-low"
    assert confidence_label(4) == "low"
    assert confidence_label(7) == "medium"
    assert confidence_label(12) == "high"


def test_single_sample_percentiles():
    stats = compute_stats([42.0])
    assert stats.median == 42.0
    assert stats.p75 == 42.0
