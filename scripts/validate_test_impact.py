#!/usr/bin/env python3
"""Validate tests/test-impact.toml registry integrity."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.test_selection.registry import (  # noqa: E402
    ALL_PYTEST_CLUSTERS,
    SAFETY_CRITICAL_CLUSTERS,
    load_registry,
    path_matches,
)

SAFETY_PRODUCTION_PREFIXES = (
    "spell_sync/pull",
    "spell_sync/push",
    "spell_sync/push_transaction.py",
    "spell_sync/push_journal.py",
    "spell_sync/push_prepared.py",
    "spell_sync/recover",
    "spell_sync/recovery",
)


def _tracked_paths(root: Path) -> set[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return set()
    return {line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}


def _format_error(error_id: str, *, cluster: str = "", target: str = "", remediation: str) -> str:
    lines = [f"[{error_id}]"]
    if cluster:
        lines.append(f"cluster: {cluster}")
    if target:
        lines.append(f"target: {target}")
    lines.append(f"remediation: {remediation}")
    return "\n".join(lines)


def validate(root: Path) -> list[str]:
    registry_path = root / "tests" / "test-impact.toml"
    errors: list[str] = []
    if not registry_path.is_file():
        return [
            _format_error(
                "TEST-IMPACT-SCHEMA-001",
                remediation="create tests/test-impact.toml",
            )
        ]

    try:
        registry = load_registry(registry_path)
    except Exception as exc:  # noqa: BLE001
        return [
            _format_error(
                "TEST-IMPACT-SCHEMA-001",
                remediation=f"fix TOML schema: {exc}",
            )
        ]

    tracked = _tracked_paths(root)
    seen_cluster_names: set[str] = set()

    for name, cluster in registry.clusters.items():
        if name in seen_cluster_names:
            errors.append(
                _format_error(
                    "TEST-IMPACT-CLUSTER-001",
                    cluster=name,
                    remediation="use unique cluster names",
                )
            )
        seen_cluster_names.add(name)

        cluster_module_targets: set[str] = set()
        for target in cluster.module_tests:
            if target in cluster_module_targets:
                errors.append(
                    _format_error(
                        "TEST-IMPACT-TARGET-002",
                        cluster=name,
                        target=target,
                        remediation="remove duplicate moduleTests target within cluster",
                    )
                )
            cluster_module_targets.add(target)
            path = root / target
            if not path.is_file():
                errors.append(
                    _format_error(
                        "TEST-IMPACT-TARGET-001",
                        cluster=name,
                        target=target,
                        remediation="replace with an existing tracked test target",
                    )
                )

        cluster_level_targets: set[str] = set()
        for target in cluster.cluster_tests:
            if target in cluster_level_targets:
                errors.append(
                    _format_error(
                        "TEST-IMPACT-TARGET-002",
                        cluster=name,
                        target=target,
                        remediation="remove duplicate clusterTests target within cluster",
                    )
                )
            cluster_level_targets.add(target)
            path = root / target
            if not path.is_file():
                errors.append(
                    _format_error(
                        "TEST-IMPACT-TARGET-001",
                        cluster=name,
                        target=target,
                        remediation="replace with an existing tracked test target",
                    )
                )

        for validator in cluster.validators:
            script = validator.split()[0]
            if script.endswith(".sh"):
                path = root / script
            else:
                path = root / script
            if not path.is_file():
                errors.append(
                    _format_error(
                        "TEST-IMPACT-VALIDATOR-001",
                        cluster=name,
                        target=validator,
                        remediation="replace with an existing validator script",
                    )
                )

        if not cluster.allow_no_match and cluster.production:
            matched = any(
                path_matches(tracked_path, cluster.production) for tracked_path in tracked
            )
            if not matched:
                errors.append(
                    _format_error(
                        "TEST-IMPACT-PATTERN-001",
                        cluster=name,
                        remediation="add a matching tracked path or set allowNoMatch=true",
                    )
                )

    for prefix in SAFETY_PRODUCTION_PREFIXES:
        covered = any(
            name in SAFETY_CRITICAL_CLUSTERS
            and any(
                path.startswith(prefix) for path in tracked if path_matches(path, spec.production)
            )
            for name, spec in registry.clusters.items()
        )
        if not covered:
            matching = [path for path in tracked if path.startswith(prefix.rstrip("*"))]
            if matching:
                errors.append(
                    _format_error(
                        "TEST-IMPACT-SAFETY-001",
                        target=matching[0],
                        remediation=(
                            "ensure safety-critical production paths map to safety clusters"
                        ),
                    )
                )

    fixture_clusters: set[str] = set()
    for fixture in registry.shared_fixtures:
        if fixture not in tracked and (root / fixture).is_file():
            tracked.add(fixture)
        for name, cluster in registry.clusters.items():
            if cluster.cluster_tests:
                fixture_clusters.add(name)
    missing_fixture_clusters = ALL_PYTEST_CLUSTERS - fixture_clusters - {"documentation"}
    if missing_fixture_clusters:
        errors.append(
            _format_error(
                "TEST-IMPACT-FIXTURE-001",
                remediation=(
                    "shared fixtures must select all pytest-bearing clusters; "
                    f"missing: {', '.join(sorted(missing_fixture_clusters))}"
                ),
            )
        )

    return errors


def main(argv: list[str] | None = None) -> int:
    del argv
    errors = validate(ROOT)
    if errors:
        sys.stderr.write("\n\n".join(errors) + "\n")
        return 1
    print("TEST_IMPACT_VALIDATION=success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
