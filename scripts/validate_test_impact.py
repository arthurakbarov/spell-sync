#!/usr/bin/env python3
"""Validate tests/test-impact.toml registry integrity."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.test_selection.registry import (  # noqa: E402
    ALL_PYTEST_CLUSTERS,
    SAFETY_CRITICAL_CLUSTERS,
    clusters_for_file,
    load_registry,
    path_matches,
)

SAFETY_PRODUCTION_PREFIXES = (
    "spell_sync/application/services/sync.py",
    "spell_sync/push",
    "spell_sync/recover",
    "spell_sync/application/services/recovery.py",
)

_HELPER_IMPORT_THRESHOLD = 2
_TEST_DEF_RE = re.compile(r"^\s*(async )?def test_", re.M)


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


def _is_collectible_name(path: str) -> bool:
    name = Path(path).name
    return name.startswith("test_") or name.endswith("_test.py")


def _module_defines_tests(text: str) -> bool:
    if _TEST_DEF_RE.search(text):
        return True
    # Re-export shims (import a test_* name into this module for collection).
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name.startswith("test_") or (alias.asname or "").startswith("test_"):
                    return True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("test_") or (alias.asname or "").startswith("test_"):
                    return True
    return False


def _module_to_tests_path(module: str) -> str | None:
    """Map an importable module name to a path under tests/ when possible."""
    if module == "tests" or module.startswith("tests."):
        return module.replace(".", "/") + ".py"
    if module == "support" or module.startswith("support."):
        return "tests/" + module.replace(".", "/") + ".py"
    if module == "tui" or module.startswith("tui."):
        return "tests/" + module.replace(".", "/") + ".py"
    # Bare helpers on tests/ sys.path (for example `from service_test_utils import ...`).
    if "." not in module:
        return f"tests/{module}.py"
    return None


def _relative_import_paths(
    importer: str,
    level: int,
    module: str | None,
    names: list[str],
) -> set[str]:
    parts = list(Path(importer.replace("\\", "/")).parts[:-1])
    if level > len(parts):
        return set()
    base_parts = parts[: len(parts) - level + 1]
    base = "/".join(base_parts)
    refs: set[str] = set()
    if module:
        refs.add(f"{base}/{module.replace('.', '/')}.py")
    else:
        for name in names:
            refs.add(f"{base}/{name}.py")
    return refs


def _import_module_paths(tree: ast.AST, importer: str) -> set[str]:
    """Return tests/-relative module paths referenced by import statements."""
    refs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names = [alias.name for alias in node.names]
            if node.level and node.level > 0:
                refs.update(_relative_import_paths(importer, node.level, node.module, names))
                continue
            if node.module:
                mapped = _module_to_tests_path(node.module)
                if mapped is not None:
                    refs.add(mapped)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                mapped = _module_to_tests_path(alias.name)
                if mapped is not None:
                    refs.add(mapped)
    return refs


def _unlisted_shared_helpers(root: Path, tracked: set[str], shared_fixtures: set[str]) -> list[str]:
    """Helpers imported by multiple modules must be listed in sharedFixtures."""
    test_files = sorted(
        path
        for path in tracked
        if path.startswith("tests/") and path.endswith(".py") and not path.endswith("/__init__.py")
    )
    texts: dict[str, str] = {}
    for rel in test_files:
        path = root / rel
        if path.is_file():
            texts[rel] = path.read_text(encoding="utf-8")

    helpers = {
        rel
        for rel, text in texts.items()
        if not (_is_collectible_name(rel) and _module_defines_tests(text))
    }
    importers: dict[str, set[str]] = defaultdict(set)
    for rel, text in texts.items():
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for imported in _import_module_paths(tree, rel):
            if imported in helpers and imported != rel:
                importers[imported].add(rel)

    errors: list[str] = []
    for helper, users in sorted(importers.items()):
        if len(users) < _HELPER_IMPORT_THRESHOLD:
            continue
        if helper in shared_fixtures:
            continue
        errors.append(
            _format_error(
                "TEST-IMPACT-FIXTURE-002",
                target=helper,
                remediation=(
                    "shared helper imported by multiple test modules must be listed in "
                    f"sharedFixtures (importers={len(users)})"
                ),
            )
        )
    return errors


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

        if name in SAFETY_CRITICAL_CLUSTERS and not cluster.validators:
            errors.append(
                _format_error(
                    "TEST-IMPACT-VALIDATOR-002",
                    cluster=name,
                    remediation=(
                        "safety-critical clusters must declare at least one validator "
                        "(for example scripts/check_architecture.py --check)"
                    ),
                )
            )

        module_only = sorted(set(cluster.module_tests) - set(cluster.cluster_tests))
        if module_only:
            errors.append(
                _format_error(
                    "TEST-IMPACT-TARGET-003",
                    cluster=name,
                    target=module_only[0],
                    remediation=(
                        "moduleTests must be a subset of clusterTests; "
                        f"missing from clusterTests: {', '.join(module_only)}"
                    ),
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
            matching = [path for path in tracked if path.startswith(prefix)]
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
            else:
                errors.append(
                    _format_error(
                        "TEST-IMPACT-SAFETY-001",
                        target=prefix,
                        remediation=(
                            "SAFETY_PRODUCTION_PREFIXES entry must match tracked paths "
                            "covered by a safety-critical cluster"
                        ),
                    )
                )

    pytest_bearing = {name for name, cluster in registry.clusters.items() if cluster.cluster_tests}
    missing_from_constant = sorted(pytest_bearing - ALL_PYTEST_CLUSTERS - {"documentation"})
    if missing_from_constant:
        errors.append(
            _format_error(
                "TEST-IMPACT-FIXTURE-001",
                remediation=(
                    "ALL_PYTEST_CLUSTERS must include every pytest-bearing cluster; "
                    f"missing: {', '.join(missing_from_constant)}"
                ),
            )
        )
    stale_constant = sorted(ALL_PYTEST_CLUSTERS - pytest_bearing)
    if stale_constant:
        errors.append(
            _format_error(
                "TEST-IMPACT-FIXTURE-001",
                remediation=(
                    "ALL_PYTEST_CLUSTERS lists clusters without clusterTests; "
                    f"remove or populate: {', '.join(stale_constant)}"
                ),
            )
        )

    if not registry.shared_fixtures:
        errors.append(
            _format_error(
                "TEST-IMPACT-FIXTURE-001",
                remediation="sharedFixtures must list at least one tracked fixture file",
            )
        )
    for fixture in registry.shared_fixtures:
        fixture_path = root / fixture
        if not fixture_path.is_file():
            errors.append(
                _format_error(
                    "TEST-IMPACT-FIXTURE-001",
                    target=fixture,
                    remediation="shared fixture path must exist",
                )
            )
            continue
        selected = clusters_for_file(fixture, registry)
        missing_selected = sorted(ALL_PYTEST_CLUSTERS - selected)
        if missing_selected:
            errors.append(
                _format_error(
                    "TEST-IMPACT-FIXTURE-001",
                    target=fixture,
                    remediation=(
                        "shared fixtures must select all pytest-bearing clusters; "
                        f"missing: {', '.join(missing_selected)}"
                    ),
                )
            )

    errors.extend(
        _unlisted_shared_helpers(
            root,
            tracked,
            set(registry.shared_fixtures),
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
