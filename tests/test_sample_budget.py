"""Sample fill-to-budget for the local edit loop."""

from __future__ import annotations

from pathlib import Path

from scripts.test_selection.registry import load_registry
from scripts.test_selection.sample_budget import (
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
    assert result.must_keep == ("tests/test_run_dev_loop_budget.py",)
    assert result.targets[0] == "tests/test_run_dev_loop_budget.py"
    assert "tests/test_run_dev_loop_budget.py" not in result.filled


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
    assert result.targets == ("tests/test_agent_context.py",)
    assert result.filled == ()
    assert result.fill_ratio == 0.0


def test_smoke_pool_preferred_when_empty_must_keep() -> None:
    registry = load_registry(ROOT / "tests" / "test-impact.toml")
    result = apply_sample_budget(
        root=ROOT,
        registry=registry,
        must_keep_targets=[],
        changed_files=["docs/FEATURE_MATRIX.md"],
        budget_seconds=60,
        seed="smoke",
    )
    assert result.filled
    assert result.filled[0] in SAMPLE_SMOKE_POOL
    assert result.fill_ratio > 0
