"""Sample fill-to-budget for the local edit loop."""

from __future__ import annotations

from pathlib import Path

from scripts.test_selection.registry import load_registry
from scripts.test_selection.sample_budget import (
    SAMPLE_MUST_KEEP_CORE,
    SAMPLE_SMOKE_POOL,
    apply_sample_budget,
)

ROOT = Path(__file__).resolve().parents[1]


def test_must_keep_always_present() -> None:
    registry = load_registry(ROOT / "tests" / "test-impact.toml")
    must = ["tests/test_run_dev_loop_budget.py"]
    result = apply_sample_budget(
        root=ROOT,
        registry=registry,
        must_keep_targets=must,
        changed_files=["scripts/run_dev_loop.py"],
        budget_seconds=60,
        seed="fixed-seed",
    )
    assert "tests/test_run_dev_loop_budget.py" in result.must_keep
    assert result.targets[0] in result.must_keep
    for core in SAMPLE_MUST_KEEP_CORE:
        if (ROOT / core).is_file():
            assert core in result.must_keep


def test_same_seed_same_plan() -> None:
    registry = load_registry(ROOT / "tests" / "test-impact.toml")
    kwargs = dict(
        root=ROOT,
        registry=registry,
        must_keep_targets=[],
        changed_files=["docs/CONTRACTS.md"],
        budget_seconds=60,
        seed="repro-seed",
    )
    a = apply_sample_budget(**kwargs)
    b = apply_sample_budget(**kwargs)
    assert a.targets == b.targets
    assert a.filled == b.filled
    assert a.fill_ratio == b.fill_ratio
    assert a.to_json_dict()["fillRatio"] == a.fill_ratio


def test_budget_zero_keeps_must_only() -> None:
    registry = load_registry(ROOT / "tests" / "test-impact.toml")
    must = ["tests/test_agent_context.py"]
    result = apply_sample_budget(
        root=ROOT,
        registry=registry,
        must_keep_targets=must,
        changed_files=[],
        budget_seconds=0,
        overhead_seconds=0,
        seed="zero",
    )
    assert "tests/test_agent_context.py" in result.must_keep
    assert result.filled == ()
    assert result.fill_ratio == 0.0


def test_smoke_pool_preferred_when_filling() -> None:
    registry = load_registry(ROOT / "tests" / "test-impact.toml")
    result = apply_sample_budget(
        root=ROOT,
        registry=registry,
        must_keep_targets=[],
        changed_files=["docs/FEATURE_MATRIX.md"],
        budget_seconds=60,
        seed="smoke",
    )
    assert result.must_keep
    assert any(path in SAMPLE_SMOKE_POOL for path in result.must_keep)
    assert result.fill_ratio > 0
