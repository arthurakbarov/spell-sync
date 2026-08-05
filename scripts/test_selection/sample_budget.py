"""Fill optional pytest targets toward the local edit-loop sample budget."""

from __future__ import annotations

import hashlib
import os
import random
import statistics
from dataclasses import dataclass
from pathlib import Path

from scripts.execution_control.history import HistoryStore
from scripts.test_selection.registry import (
    DEV_SCOPE_EXCLUDED_TESTS,
    SAFETY_CRITICAL_CLUSTERS,
    Registry,
    clusters_for_file,
)

# Default per-file cost when no history is available (seconds).
# Prefer under-filling the wall budget over exceeding the L0 SLA.
DEFAULT_TARGET_COST_SECONDS = 6.0
# Reserve wall time for ruff / validators / startup on L0.
DEFAULT_OVERHEAD_SECONDS = 15.0
# Always prefer these module tests as must-keep core when present on disk.
SAMPLE_MUST_KEEP_CORE: tuple[str, ...] = (
    "tests/test_agent_context.py",
    "tests/test_run_dev_loop_budget.py",
    "tests/test_public_documentation_contract.py",
    "tests/test_test_planner.py",
)
# Prefer these next when filling the optional pool.
SAMPLE_SMOKE_POOL: tuple[str, ...] = (
    *SAMPLE_MUST_KEEP_CORE,
    "tests/test_cli_import_surface.py",
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

    def to_json_dict(self) -> dict[str, object]:
        return {
            "sampled": True,
            "samplingBudgetSeconds": self.budget_seconds,
            "samplingSeed": self.seed,
            "mustKeep": list(self.must_keep),
            "filled": list(self.filled),
            "omitted": list(self.omitted),
            "samplingUsedSeconds": self.used_seconds,
            "fillRatio": self.fill_ratio,
            "targets": list(self.targets),
        }


def _stable_seed(changed_files: list[str], budget_seconds: float) -> str:
    explicit = os.environ.get("SPELL_SYNC_SAMPLE_SEED", "").strip()
    if explicit:
        return explicit
    payload = "|".join(sorted(changed_files)) + f"|{budget_seconds:.0f}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def sample_execution_id(path: str) -> str:
    return f"sample-target:{path}"


def target_cost_seconds(
    path: str,
    *,
    default: float = DEFAULT_TARGET_COST_SECONDS,
    history: HistoryStore | None = None,
) -> float:
    """Prefer history median for this sample target; else default cost."""
    close = False
    store = history
    if store is None:
        try:
            store = HistoryStore.open()
            close = True
        except OSError:
            return float(default)
    try:
        durations = store.fetch_profile_durations(
            execution_id=sample_execution_id(path),
            limit=20,
        )
        if durations:
            return max(1.0, float(statistics.median(durations)))
    finally:
        if close and store is not None:
            store.close()
    return float(default)


def expand_must_keep(
    registry: Registry,
    root: Path,
    plan_targets: list[str],
    *,
    changed_files: list[str],
) -> list[str]:
    """Plan targets + on-disk smoke core + safety module tests when safety clusters map."""
    ordered: list[str] = []
    seen: set[str] = set()

    def _add(path: str) -> None:
        if path in seen or path in DEV_SCOPE_EXCLUDED_TESTS:
            return
        if not (root / path).is_file():
            return
        seen.add(path)
        ordered.append(path)

    for path in plan_targets:
        _add(path)
    for path in SAMPLE_MUST_KEEP_CORE:
        _add(path)

    # If any changed path maps into a safety-critical cluster, keep that cluster's module tests.
    safety_hit: set[str] = set()
    for path in changed_files:
        for name in clusters_for_file(path, registry, dev_scope=True):
            if name in SAFETY_CRITICAL_CLUSTERS:
                safety_hit.add(name)
    for name in sorted(safety_hit):
        spec = registry.clusters.get(name)
        if spec is None:
            continue
        for path in spec.module_tests:
            _add(path)
    return ordered


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
    target_cost_seconds_default: float = DEFAULT_TARGET_COST_SECONDS,
    seed: str | None = None,
    history: HistoryStore | None = None,
) -> SampleBudgetResult:
    """Keep must-keep targets; fill optional module tests until budget remaining is used."""
    must_ordered = expand_must_keep(
        registry,
        root,
        must_keep_targets,
        changed_files=changed_files,
    )
    must_set = set(must_ordered)
    seed_s = seed if seed is not None else _stable_seed(changed_files, budget_seconds)
    remaining = max(0.0, float(budget_seconds) - float(overhead_seconds))
    used = 0.0
    for path in must_ordered:
        cost = target_cost_seconds(
            path,
            default=target_cost_seconds_default,
            history=history,
        )
        used += cost
    remaining -= used

    optional = _optional_pool(registry, root, must_set)
    rng = random.Random(seed_s)
    smoke_set = set(SAMPLE_SMOKE_POOL)
    head = [p for p in optional if p in smoke_set]
    tail = [p for p in optional if p not in smoke_set]
    rng.shuffle(tail)
    ordered_optional = head + tail

    filled: list[str] = []
    for path in ordered_optional:
        cost = target_cost_seconds(
            path,
            default=target_cost_seconds_default,
            history=history,
        )
        if remaining < cost:
            continue
        filled.append(path)
        remaining -= cost
        used += cost

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
