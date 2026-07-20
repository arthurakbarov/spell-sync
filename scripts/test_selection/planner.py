"""Build change-aware test plans."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.test_selection.registry import (
    ALL_PYTEST_CLUSTERS,
    Registry,
    clusters_for_file,
    dedupe_sorted,
    is_docs_only,
    load_registry,
)

PLAN_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class TestPlan:
    schema_version: int
    changed_files: tuple[str, ...]
    clusters: tuple[str, ...]
    pytest_targets: tuple[str, ...]
    static_targets: tuple[str, ...]
    validators: tuple[str, ...]
    requires_full_ci: bool
    reasons: tuple[str, ...]
    command: tuple[str, ...] = ()

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": self.schema_version,
            "changedFiles": list(self.changed_files),
            "clusters": list(self.clusters),
            "pytestTargets": list(self.pytest_targets),
            "staticTargets": list(self.static_targets),
            "validators": list(self.validators),
            "requiresFullCi": self.requires_full_ci,
            "reasons": list(self.reasons),
            "command": list(self.command),
        }


def _collect_cluster_tests(clusters: set[str], registry: Registry) -> list[str]:
    tests: list[str] = []
    for name in sorted(clusters):
        if name == "_test_file":
            continue
        spec = registry.clusters.get(name)
        if spec is not None:
            tests.extend(spec.tests)
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


def _pytest_command(targets: list[str], python: str = "python3") -> tuple[str, ...]:
    if not targets:
        return ()
    return (python, "-m", "pytest", *targets, "-q")


def build_plan(
    root: Path,
    changed_files: list[str],
    *,
    registry: Registry | None = None,
    cluster_override: str | None = None,
    target_override: str | None = None,
    python: str = "python3",
) -> TestPlan:
    registry = registry or load_registry(root / "tests" / "test-impact.toml")
    reasons: list[str] = []
    clusters: set[str] = set()
    pytest_targets: list[str] = []
    validators: list[str] = []
    static_targets: list[str] = []
    requires_full_ci = True

    if target_override:
        pytest_targets = [target_override]
        reasons.append(f"explicit target override: {target_override}")
        requires_full_ci = True
        command = _pytest_command(pytest_targets, python)
        return TestPlan(
            schema_version=PLAN_SCHEMA_VERSION,
            changed_files=tuple(changed_files),
            clusters=(),
            pytest_targets=tuple(pytest_targets),
            static_targets=(),
            validators=(),
            requires_full_ci=requires_full_ci,
            reasons=tuple(reasons),
            command=command,
        )

    if cluster_override:
        clusters.add(cluster_override)
        reasons.append(f"explicit cluster override: {cluster_override}")
    elif not changed_files:
        reasons.append("no changed files detected")
    else:
        docs_only = all(is_docs_only(path, registry) for path in changed_files)
        test_only = all(
            path.startswith("tests/") and path.endswith(".py") for path in changed_files
        )
        if docs_only:
            clusters.add("documentation")
            reasons.append("docs-only changes")
            requires_full_ci = True
        elif test_only:
            pytest_targets = list(changed_files)
            reasons.append("test file changes only")
            requires_full_ci = True
        else:
            per_file_clusters: set[str] = set()
            direct_tests: list[str] = []
            for path in changed_files:
                file_clusters = clusters_for_file(path, registry)
                if "_test_file" in file_clusters:
                    direct_tests.append(path)
                    continue
                per_file_clusters.update(file_clusters)
            if direct_tests:
                pytest_targets.extend(direct_tests)
            clusters.update(per_file_clusters)
            if clusters:
                joined = ", ".join(sorted(clusters))
                reasons.append(f"mapped clusters: {joined}")
            if not clusters and not pytest_targets:
                clusters.add("packaging")
                reasons.append("conservative fallback for unknown production file")

    if clusters:
        pytest_targets.extend(_collect_cluster_tests(clusters, registry))
        validators.extend(_collect_validators(clusters, registry))
        static_targets.extend(_collect_static_targets(clusters, registry))

    pytest_targets = dedupe_sorted(pytest_targets)
    validators = dedupe_sorted(validators)
    static_targets = dedupe_sorted(static_targets)

    if "documentation" in clusters and len(clusters) == 1:
        command: tuple[str, ...] = ()
    elif pytest_targets:
        command = _pytest_command(pytest_targets, python)
    else:
        command = ()

    return TestPlan(
        schema_version=PLAN_SCHEMA_VERSION,
        changed_files=tuple(changed_files),
        clusters=tuple(sorted(clusters)),
        pytest_targets=tuple(pytest_targets),
        static_targets=tuple(static_targets),
        validators=tuple(validators),
        requires_full_ci=requires_full_ci,
        reasons=tuple(reasons),
        command=command,
    )


def safety_clusters_required(changed_files: list[str], registry: Registry) -> set[str]:
    required: set[str] = set()
    for path in changed_files:
        for cluster_name in clusters_for_file(path, registry):
            if cluster_name in ALL_PYTEST_CLUSTERS and cluster_name in {
                "pull",
                "push",
                "transaction",
                "recovery",
            }:
                required.add(cluster_name)
    return required
