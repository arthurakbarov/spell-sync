"""Build change-aware test plans."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.ci_impact.registry import (
    classify_path,
)
from scripts.ci_impact.registry import (
    load_registry as load_ci_impact_registry,
)
from scripts.ci_impact.registry import (
    requires_full_ci as class_requires_full_ci,
)
from scripts.test_selection.registry import (
    DEV_SCOPE_EXCLUDED_TESTS,
    SAFETY_CRITICAL_CLUSTERS,
    Registry,
    clusters_for_file,
    dedupe_sorted,
    is_docs_only,
    load_registry,
    required_safety_clusters,
)

PLAN_SCHEMA_VERSION = 2
ValidationLevel = int


@dataclass(frozen=True, slots=True)
class TestPlan:
    schema_version: int
    changed_files: tuple[str, ...]
    clusters: tuple[str, ...]
    required_clusters: tuple[str, ...]
    pytest_targets: tuple[str, ...]
    static_targets: tuple[str, ...]
    validators: tuple[str, ...]
    requires_full_ci: bool
    validation_level: ValidationLevel
    final_focused_evidence: bool
    reasons: tuple[str, ...]
    command: tuple[str, ...] = ()

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": self.schema_version,
            "changedFiles": list(self.changed_files),
            "clusters": list(self.clusters),
            "requiredClusters": list(self.required_clusters),
            "pytestTargets": list(self.pytest_targets),
            "staticTargets": list(self.static_targets),
            "validators": list(self.validators),
            "requiresFullCi": self.requires_full_ci,
            "validationLevel": self.validation_level,
            "finalFocusedEvidence": self.final_focused_evidence,
            "reasons": list(self.reasons),
            "command": list(self.command),
        }


def _collect_tests(
    clusters: set[str],
    registry: Registry,
    *,
    level: str,
    cluster_level_for: set[str] | None = None,
) -> list[str]:
    cluster_level_for = cluster_level_for or set()
    tests: list[str] = []
    for name in sorted(clusters):
        if name == "_test_file":
            continue
        spec = registry.clusters.get(name)
        if spec is None:
            continue
        effective = "cluster" if name in cluster_level_for else level
        if effective == "module":
            tests.extend(spec.module_tests)
        else:
            tests.extend(spec.cluster_tests)
    return dedupe_sorted(tests)


def _collect_validators(clusters: set[str], registry: Registry) -> list[str]:
    validators: list[str] = []
    for name in sorted(clusters):
        spec = registry.clusters.get(name)
        if spec is not None:
            validators.extend(spec.validators)
    return dedupe_sorted(validators)


def _collect_static_targets(clusters: set[str], registry: Registry) -> list[str]:
    static: list[str] = []
    for name in sorted(clusters):
        spec = registry.clusters.get(name)
        if spec is not None:
            static.extend(spec.static_targets)
    return dedupe_sorted(static)


def _static_targets_for_changed_files(changed_files: list[str]) -> list[str]:
    static: list[str] = []
    for path in changed_files:
        if path == "pyproject.toml":
            static.append("spell_sync")
        elif path.startswith("spell_sync/") and path.endswith(".py"):
            static.append(path)
    return dedupe_sorted(static)


def _pytest_command(targets: list[str], python: str = "python3") -> tuple[str, ...]:
    if not targets:
        return ()
    return (python, "-m", "pytest", *targets, "-q", "--durations=10")


def _requires_full_ci(root: Path, changed_files: list[str]) -> bool:
    """Derive plan.requires_full_ci from CI impact classes (not always True)."""
    if not changed_files:
        return True

    ci_registry = load_ci_impact_registry(root / "ci" / "ci-impact.toml")
    return any(class_requires_full_ci(classify_path(path, ci_registry)) for path in changed_files)


def _clusters_and_direct_tests(
    changed_files: list[str],
    registry: Registry,
    *,
    dev_scope: bool = False,
) -> tuple[set[str], list[str]]:
    clusters: set[str] = set()
    direct_tests: list[str] = []
    for path in changed_files:
        file_clusters = clusters_for_file(path, registry, dev_scope=dev_scope)
        if "_test_file" in file_clusters:
            direct_tests.append(path)
            continue
        clusters.update(file_clusters)
    return clusters, direct_tests


def build_plan(
    root: Path,
    changed_files: list[str],
    *,
    registry: Registry | None = None,
    cluster_override: str | None = None,
    target_override: str | None = None,
    level: str = "cluster",
    python: str = "python3",
    dev_scope: bool = False,
    include_safety_cluster_tests: bool = False,
) -> TestPlan:
    registry = registry or load_registry(root / "tests" / "test-impact.toml")
    reasons: list[str] = []
    clusters: set[str] = set()
    pytest_targets: list[str] = []
    validators: list[str] = []
    static_targets: list[str] = []
    requires_full_ci = _requires_full_ci(root, changed_files)
    effective_level = level
    if dev_scope and level == "cluster":
        # Local commit gate: module tests by default; cluster fan-out only when safety-required.
        effective_level = "module"
    validation_level: ValidationLevel = 2 if effective_level == "cluster" else 1
    final_focused_evidence = effective_level == "cluster"

    if target_override:
        pytest_targets = [target_override]
        reasons.append(f"Level 0 diagnostic target: {target_override}")
        return TestPlan(
            schema_version=PLAN_SCHEMA_VERSION,
            changed_files=tuple(changed_files),
            clusters=(),
            required_clusters=(),
            pytest_targets=tuple(pytest_targets),
            static_targets=(),
            validators=(),
            requires_full_ci=True,
            validation_level=0,
            final_focused_evidence=False,
            reasons=tuple(reasons),
            command=_pytest_command(pytest_targets, python),
        )

    required = required_safety_clusters(changed_files, registry, dev_scope=dev_scope)

    if not changed_files:
        reasons.append("no changed files detected")
    else:
        docs_only = all(is_docs_only(path, registry) for path in changed_files)
        shared_fixture_paths = frozenset(registry.shared_fixtures) | frozenset(
            {"tests/conftest.py"}
        )
        test_only = all(
            path.startswith("tests/") and path.endswith(".py") and path not in shared_fixture_paths
            for path in changed_files
        )
        if docs_only:
            clusters.add("documentation")
            if any(
                path.startswith(".cursor/") or "AGENT" in path.upper() for path in changed_files
            ):
                clusters.add("agent-workflow")
            reasons.append("docs-only changes")
        elif test_only:
            pytest_targets = list(changed_files)
            reasons.append("test file changes only")
        else:
            mapped, direct_tests = _clusters_and_direct_tests(
                changed_files, registry, dev_scope=dev_scope
            )
            clusters.update(mapped)
            if direct_tests:
                pytest_targets.extend(direct_tests)
                reasons.append(f"changed test files: {', '.join(sorted(direct_tests))}")
            if clusters:
                reasons.append(f"mapped clusters: {', '.join(sorted(clusters))}")
            if not clusters and not pytest_targets:
                clusters.add("packaging")
                reasons.append("conservative fallback for unknown production file")
            if dev_scope and any(path in shared_fixture_paths for path in changed_files):
                reasons.append("dev-scope: shared fixtures map to test-selection only")

    if cluster_override:
        clusters.add(cluster_override)
        reasons.append(f"added cluster override: {cluster_override}")

    clusters.update(required)
    if required:
        reasons.append(f"required safety clusters: {', '.join(sorted(required))}")

    if clusters:
        cluster_level_for: set[str] = set()
        if include_safety_cluster_tests:
            cluster_level_for = (clusters | required) & SAFETY_CRITICAL_CLUSTERS
            if cluster_level_for:
                validation_level = 2
                final_focused_evidence = True
                reasons.append(
                    "safety cluster tests: " + ", ".join(sorted(cluster_level_for)),
                )
        pytest_targets.extend(
            _collect_tests(
                clusters,
                registry,
                level=effective_level,
                cluster_level_for=cluster_level_for,
            )
        )
        validators.extend(_collect_validators(clusters, registry))
        static_targets.extend(_collect_static_targets(clusters, registry))

    static_targets.extend(_static_targets_for_changed_files(changed_files))

    pytest_targets = dedupe_sorted(pytest_targets)
    validators = dedupe_sorted(validators)
    static_targets = dedupe_sorted(static_targets)

    if dev_scope and pytest_targets:
        filtered = [path for path in pytest_targets if path not in DEV_SCOPE_EXCLUDED_TESTS]
        if len(filtered) != len(pytest_targets):
            reasons.append("dev-scope: deferred wheel-smoke tests to L2")
            pytest_targets = filtered

    if "documentation" in clusters and not pytest_targets:
        command: tuple[str, ...] = ()
    elif pytest_targets:
        command = _pytest_command(pytest_targets, python)
    else:
        command = ()

    return TestPlan(
        schema_version=PLAN_SCHEMA_VERSION,
        changed_files=tuple(changed_files),
        clusters=tuple(sorted(clusters)),
        required_clusters=tuple(sorted(required)),
        pytest_targets=tuple(pytest_targets),
        static_targets=tuple(static_targets),
        validators=tuple(validators),
        requires_full_ci=requires_full_ci,
        validation_level=validation_level,
        final_focused_evidence=final_focused_evidence,
        reasons=tuple(reasons),
        command=command,
    )
