"""Load and validate execution budget registry."""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path

REGISTRY_REL_PATH = "tests/execution-budget.toml"
SCHEMA_VERSION = 1
ALLOWED_TOP_KEYS = frozenset(
    {
        "schemaVersion",
        "meta",
        "profiles",
        "childMappings",
    }
)
ALLOWED_META_KEYS = frozenset(
    {
        "registryPath",
        "globalHardCapSeconds",
        "editLoopBudgetSeconds",
        "sessionWindowSeconds",
        "sessionTestTimeShareWarn",
        "historyWindow",
        "historyMaxRaw",
        "normalLearningWindow",
    }
)
ALLOWED_PROFILE_KEYS = frozenset(
    {
        "kind",
        "executionId",
        "initialExpectedSeconds",
        "initialSoftSeconds",
        "stallFloorSeconds",
        "stallCapSeconds",
        "initialHardSeconds",
        "hardCapSeconds",
        "diagnosticHardSeconds",
        "terminationGraceSeconds",
        "progressContract",
        "historyWindow",
        "minimumSamples",
        "parentRetries",
        "diagnosticRetries",
        "source",
        "workloadCost",
    }
)
ALLOWED_WORKLOAD_COST_KEYS = frozenset(
    {
        "fixedSeconds",
        "perTestFileSeconds",
        "perTestNodeSeconds",
        "maximumBootstrapSeconds",
    }
)


@dataclass(frozen=True, slots=True)
class WorkloadCost:
    fixed_seconds: float
    per_test_file_seconds: float
    per_test_node_seconds: float
    maximum_bootstrap_seconds: float


@dataclass(frozen=True, slots=True)
class Profile:
    profile_id: str
    kind: str
    execution_id: str
    initial_expected_seconds: float
    initial_soft_seconds: float
    stall_floor_seconds: float
    stall_cap_seconds: float
    initial_hard_seconds: float
    hard_cap_seconds: float
    diagnostic_hard_seconds: float
    termination_grace_seconds: float
    progress_contract: str
    history_window: int
    minimum_samples: int
    parent_retries: int
    diagnostic_retries: int
    source: str
    workload_cost: WorkloadCost | None = None


@dataclass(frozen=True, slots=True)
class ChildMapping:
    execution_id: str
    profile_id: str
    parent_execution_id: str


@dataclass(frozen=True, slots=True)
class ExecutionBudgetRegistry:
    schema_version: int
    path: Path
    global_hard_cap_seconds: float
    edit_loop_budget_seconds: float
    session_window_seconds: int
    session_test_time_share_warn: float
    history_window: int
    history_max_raw: int
    normal_learning_window: int
    profiles: dict[str, Profile]
    child_mappings: dict[str, ChildMapping]


def _require_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be > 0")


def _validate_profile(profile_id: str, payload: dict[str, object]) -> list[str]:
    errors: list[str] = []
    unknown = set(payload) - ALLOWED_PROFILE_KEYS
    if unknown:
        errors.append(f"profile {profile_id}: unknown keys {sorted(unknown)}")
    try:
        expected = float(payload["initialExpectedSeconds"])  # type: ignore[arg-type]
        soft = float(payload["initialSoftSeconds"])  # type: ignore[arg-type]
        hard = float(payload["initialHardSeconds"])  # type: ignore[arg-type]
        hard_cap = float(payload["hardCapSeconds"])  # type: ignore[arg-type]
        diag = float(payload["diagnosticHardSeconds"])  # type: ignore[arg-type]
        grace = float(payload["terminationGraceSeconds"])  # type: ignore[arg-type]
        parent_retries = int(payload["parentRetries"])  # type: ignore[arg-type]
        diagnostic_retries = int(payload["diagnosticRetries"])  # type: ignore[arg-type]
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"profile {profile_id}: invalid numeric fields ({exc})")
        return errors
    if not (expected > 0 and expected < soft < hard <= hard_cap):
        errors.append(f"profile {profile_id}: expected < soft < hard <= hard_cap violated")
    if diag > 15:
        errors.append(f"profile {profile_id}: diagnosticHardSeconds must be <= 15")
    if grace <= 0 or grace > 60:
        errors.append(f"profile {profile_id}: terminationGraceSeconds out of bounds")
    if parent_retries != 0:
        errors.append(f"profile {profile_id}: parentRetries must be 0")
    if diagnostic_retries > 1:
        errors.append(f"profile {profile_id}: diagnosticRetries must be <= 1")
    stall_floor = float(payload.get("stallFloorSeconds", 0) or 0)
    stall_cap = float(payload.get("stallCapSeconds", 0) or 0)
    contract = str(payload.get("progressContract", "") or "")
    if contract and not (stall_floor > 0 and stall_cap >= stall_floor):
        errors.append(f"profile {profile_id}: stall-sensitive profile requires stall bounds")
    return errors


def _parse_workload_cost(profile_id: str, payload: dict[str, object]) -> WorkloadCost | None:
    raw = payload.get("workloadCost")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"profile {profile_id}: workloadCost must be a table")
    unknown = set(raw) - ALLOWED_WORKLOAD_COST_KEYS
    if unknown:
        raise ValueError(f"profile {profile_id}: unknown workloadCost keys {sorted(unknown)}")
    fixed = float(raw.get("fixedSeconds", 0) or 0)
    per_file = float(raw.get("perTestFileSeconds", 0) or 0)
    per_node = float(raw.get("perTestNodeSeconds", 0) or 0)
    maximum = float(raw.get("maximumBootstrapSeconds", 0) or 0)
    if fixed <= 0 and per_file <= 0 and per_node <= 0:
        raise ValueError(f"profile {profile_id}: workloadCost requires positive unit cost")
    if maximum <= 0:
        raise ValueError(f"profile {profile_id}: maximumBootstrapSeconds must be > 0")
    return WorkloadCost(
        fixed_seconds=fixed,
        per_test_file_seconds=per_file,
        per_test_node_seconds=per_node,
        maximum_bootstrap_seconds=maximum,
    )


def validate_registry(registry: ExecutionBudgetRegistry) -> list[str]:
    errors: list[str] = []
    if registry.global_hard_cap_seconds > 1800:
        errors.append("globalHardCapSeconds exceeds 30 minutes")
    seen_execution_ids: dict[str, str] = {}
    required = {
        "focused-module",
        "focused-cluster",
        "pre-final",
        "full-ci",
        "ci-child",
        "snapshot-tests",
        "diagnostic-pytest",
        "unknown-check",
        "focused-pytest",
    }
    missing = required - set(registry.profiles)
    if missing:
        errors.append(f"missing required profiles: {sorted(missing)}")
    for profile_id, profile in registry.profiles.items():
        if profile.execution_id in seen_execution_ids:
            errors.append(f"duplicate execution ID {profile.execution_id}")
        seen_execution_ids[profile.execution_id] = profile_id
        if profile.hard_cap_seconds > registry.global_hard_cap_seconds:
            errors.append(f"profile {profile_id}: hardCap exceeds global cap")
    for child_id, mapping in registry.child_mappings.items():
        if mapping.profile_id not in registry.profiles:
            errors.append(f"child mapping {child_id}: unknown profile")
    return errors


def load_registry(path: Path) -> ExecutionBudgetRegistry:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("execution budget registry must be a table")
    unknown_top = set(data) - ALLOWED_TOP_KEYS
    if unknown_top:
        raise ValueError(f"unknown top-level keys: {sorted(unknown_top)}")
    schema_version = data.get("schemaVersion")
    if schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported schemaVersion: {schema_version!r}")
    meta = data.get("meta") or {}
    if not isinstance(meta, dict):
        raise ValueError("meta must be a table")
    unknown_meta = set(meta) - ALLOWED_META_KEYS
    if unknown_meta:
        raise ValueError(f"unknown meta keys: {sorted(unknown_meta)}")

    profiles_raw = data.get("profiles") or {}
    if not isinstance(profiles_raw, dict):
        raise ValueError("profiles must be a table")
    profiles: dict[str, Profile] = {}
    for profile_id, payload in profiles_raw.items():
        if not isinstance(payload, dict):
            raise ValueError(f"profile {profile_id} must be a table")
        errors = _validate_profile(profile_id, payload)
        if errors:
            raise ValueError("; ".join(errors))
        profiles[profile_id] = Profile(
            profile_id=profile_id,
            kind=str(payload["kind"]),
            execution_id=str(payload["executionId"]),
            initial_expected_seconds=float(payload["initialExpectedSeconds"]),
            initial_soft_seconds=float(payload["initialSoftSeconds"]),
            stall_floor_seconds=float(payload.get("stallFloorSeconds", 0) or 0),
            stall_cap_seconds=float(payload.get("stallCapSeconds", 0) or 0),
            initial_hard_seconds=float(payload["initialHardSeconds"]),
            hard_cap_seconds=float(payload["hardCapSeconds"]),
            diagnostic_hard_seconds=float(payload["diagnosticHardSeconds"]),
            termination_grace_seconds=float(payload["terminationGraceSeconds"]),
            progress_contract=str(payload.get("progressContract", "") or ""),
            history_window=int(payload.get("historyWindow", meta.get("historyWindow", 30))),
            minimum_samples=int(payload.get("minimumSamples", 3)),
            parent_retries=int(payload["parentRetries"]),
            diagnostic_retries=int(payload["diagnosticRetries"]),
            source=str(payload.get("source", "")),
            workload_cost=_parse_workload_cost(profile_id, payload),
        )

    child_raw = data.get("childMappings") or {}
    child_mappings: dict[str, ChildMapping] = {}
    if isinstance(child_raw, dict):
        for child_id, mapping in child_raw.items():
            if not isinstance(mapping, dict):
                raise ValueError(f"child mapping {child_id} must be a table")
            child_mappings[child_id] = ChildMapping(
                execution_id=child_id,
                profile_id=str(mapping["profile"]),
                parent_execution_id=str(mapping["parent"]),
            )

    registry = ExecutionBudgetRegistry(
        schema_version=int(schema_version),
        path=path,
        global_hard_cap_seconds=float(meta.get("globalHardCapSeconds", 1800)),
        edit_loop_budget_seconds=float(meta.get("editLoopBudgetSeconds", 120)),
        session_window_seconds=int(meta.get("sessionWindowSeconds", 1800)),
        session_test_time_share_warn=float(meta.get("sessionTestTimeShareWarn", 0.6)),
        history_window=int(meta.get("historyWindow", 30)),
        history_max_raw=int(meta.get("historyMaxRaw", 500)),
        normal_learning_window=int(meta.get("normalLearningWindow", 30)),
        profiles=profiles,
        child_mappings=child_mappings,
    )
    errors = validate_registry(registry)
    if errors:
        raise ValueError("; ".join(errors))
    return registry


def registry_digest(registry: ExecutionBudgetRegistry) -> str:
    return hashlib.sha256(registry.path.read_bytes()).hexdigest()


def profile_for_execution_id(
    registry: ExecutionBudgetRegistry,
    execution_id: str,
) -> Profile:
    mapping = registry.child_mappings.get(execution_id)
    if mapping is not None:
        return registry.profiles[mapping.profile_id]
    for profile in registry.profiles.values():
        if profile.execution_id == execution_id:
            return profile
    return registry.profiles["unknown-check"]
