"""Build change-aware test plans."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.test_selection.registry import (
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
) -> list[str]:
    tests: list[str] = []
    for name in sorted(clusters):
        if name == "_test_file":
            continue
        spec = registry.clusters.get(name)
        if spec is None:
            continue
        if level == "module":
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


def _clusters_from_changes(changed_files: list[str], registry: Registry) -> set[str]:
    clusters: set[str] = set()
    direct_tests: list[str] = []
    for path in changed_files:
        file_clusters = clusters_for_file(path, registry)
        if "_test_file" in file_clusters:
            direct_tests.append(path)
            continue
        clusters.update(file_clusters)
    if direct_tests and not clusters:
        return clusters
    return clusters


def build_plan(
    root: Path,
    changed_files: list[str],
    *,
    registry: Registry | None = None,
    cluster_override: str | None = None,
    target_override: str | None = None,
    level: str = "cluster",
    python: str = "python3",
) -> TestPlan:
    registry = registry or load_registry(root / "tests" / "test-impact.toml")
    reasons: list[str] = []
    clusters: set[str] = set()
    pytest_targets: list[str] = []
    validators: list[str] = []
    static_targets: list[str] = []
    requires_full_ci = True
    validation_level: ValidationLevel = 2 if level == "cluster" else 1
    final_focused_evidence = level == "cluster"

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

    required = required_safety_clusters(changed_files, registry)

    if not changed_files:
        reasons.append("no changed files detected")
    else:
        docs_only = all(is_docs_only(path, registry) for path in changed_files)
        test_only = all(
            path.startswith("tests/") and path.endswith(".py") for path in changed_files
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
            clusters.update(_clusters_from_changes(changed_files, registry))
            if clusters:
                reasons.append(f"mapped clusters: {', '.join(sorted(clusters))}")
            if not clusters and not pytest_targets:
                clusters.add("packaging")
                reasons.append("conservative fallback for unknown production file")

    if cluster_override:
        clusters.add(cluster_override)
        reasons.append(f"added cluster override: {cluster_override}")

    clusters.update(required)
    if required:
        reasons.append(f"required safety clusters: {', '.join(sorted(required))}")

    if clusters:
        pytest_targets.extend(_collect_tests(clusters, registry, level=level))
        validators.extend(_collect_validators(clusters, registry))
        static_targets.extend(_collect_static_targets(clusters, registry))

    static_targets.extend(_static_targets_for_changed_files(changed_files))

    pytest_targets = dedupe_sorted(pytest_targets)
    validators = dedupe_sorted(validators)
    static_targets = dedupe_sorted(static_targets)

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
