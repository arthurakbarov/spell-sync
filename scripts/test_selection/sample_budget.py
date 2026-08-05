"""Fill optional pytest targets toward the local edit-loop sample budget."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from pathlib import Path

from scripts.test_selection.registry import DEV_SCOPE_EXCLUDED_TESTS, Registry

# Default per-file cost when no history is available (seconds).
# Prefer under-filling the wall budget over exceeding the L0 SLA.
DEFAULT_TARGET_COST_SECONDS = 6.0
# Reserve wall time for ruff / validators / startup on L0.
DEFAULT_OVERHEAD_SECONDS = 15.0
# Prefer these module tests first when the affected plan is empty or tiny.
SAMPLE_SMOKE_POOL: tuple[str, ...] = (
    "tests/test_agent_context.py",
    "tests/test_run_dev_loop_budget.py",
    "tests/test_cli_import_surface.py",
    "tests/test_public_documentation_contract.py",
    "tests/test_test_planner.py",
)


@dataclass(frozen=True, slots=True)
class SampleBudgetResult:
    targets: tuple[str, ...]
    must_keep: tuple[str, ...]
    filled: tuple[str, ...]
    omitted: tuple[str, ...]
    budget_seconds: float
    used_seconds: float
    fill_ratio: float
    seed: str


def _stable_seed(changed_files: list[str], budget_seconds: float) -> str:
    payload = "|".join(sorted(changed_files)) + f"|{budget_seconds:.0f}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _optional_pool(registry: Registry, root: Path, must_keep: set[str]) -> list[str]:
    seen: set[str] = set()
    pool: list[str] = []
    for path in SAMPLE_SMOKE_POOL:
        if path in must_keep or path in DEV_SCOPE_EXCLUDED_TESTS:
            continue
        if (root / path).is_file() and path not in seen:
            seen.add(path)
            pool.append(path)
    for name in sorted(registry.clusters):
        spec = registry.clusters[name]
        for path in spec.module_tests:
            if path in must_keep or path in DEV_SCOPE_EXCLUDED_TESTS:
                continue
            if (root / path).is_file() and path not in seen:
                seen.add(path)
                pool.append(path)
    return pool


def apply_sample_budget(
    *,
    root: Path,
    registry: Registry,
    must_keep_targets: list[str],
    changed_files: list[str],
    budget_seconds: float,
    overhead_seconds: float = DEFAULT_OVERHEAD_SECONDS,
    target_cost_seconds: float = DEFAULT_TARGET_COST_SECONDS,
    seed: str | None = None,
) -> SampleBudgetResult:
    """Keep must-keep targets; fill optional module tests until budget remaining is used."""
    must_ordered = list(dict.fromkeys(must_keep_targets))
    must_set = set(must_ordered)
    seed_s = seed if seed is not None else _stable_seed(changed_files, budget_seconds)
    remaining = max(0.0, float(budget_seconds) - float(overhead_seconds))
    used = len(must_ordered) * float(target_cost_seconds)
    remaining -= used

    optional = _optional_pool(registry, root, must_set)
    rng = random.Random(seed_s)
    # Prefer smoke pool order already at front; shuffle the rest deterministically.
    smoke_set = set(SAMPLE_SMOKE_POOL)
    head = [p for p in optional if p in smoke_set]
    tail = [p for p in optional if p not in smoke_set]
    rng.shuffle(tail)
    ordered_optional = head + tail

    filled: list[str] = []
    for path in ordered_optional:
        if remaining < target_cost_seconds:
            break
        filled.append(path)
        remaining -= target_cost_seconds
        used += target_cost_seconds

    kept = must_ordered + filled
    omitted = [p for p in ordered_optional if p not in set(filled)]
    fill = round(used / budget_seconds, 4) if budget_seconds > 0 else 0.0
    return SampleBudgetResult(
        targets=tuple(kept),
        must_keep=tuple(must_ordered),
        filled=tuple(filled),
        omitted=tuple(omitted),
        budget_seconds=float(budget_seconds),
        used_seconds=round(used, 2),
        fill_ratio=fill,
        seed=seed_s,
    )
