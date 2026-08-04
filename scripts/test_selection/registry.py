"""Load and match the test impact registry."""

from __future__ import annotations

import fnmatch
import tomllib
from dataclasses import dataclass
from pathlib import Path

SAFETY_CRITICAL_CLUSTERS = frozenset({"pull", "push", "transaction", "recovery"})
CONSERVATIVE_FALLBACK_CLUSTER = "packaging"
# Wheel/installed smoke stays L2-only; keep L0/L1 packaging gates under the commit SLA.
DEV_SCOPE_EXCLUDED_TESTS = frozenset({"tests/test_installed_workflow.py"})
ALL_PYTEST_CLUSTERS = frozenset(
    {
        "runtime",
        "configuration",
        "pull",
        "push",
        "transaction",
        "recovery",
        "tui",
        "cli-json",
        "packaging",
        "agent-workflow",
        "diagnostics-events",
        "execution-control",
        "test-selection",
        "user-documentation",
    }
)


@dataclass(frozen=True, slots=True)
class ClusterSpec:
    name: str
    production: tuple[str, ...]
    module_tests: tuple[str, ...]
    cluster_tests: tuple[str, ...]
    validators: tuple[str, ...] = ()
    static_targets: tuple[str, ...] = ()
    allow_no_match: bool = False


@dataclass(frozen=True, slots=True)
class Registry:
    clusters: dict[str, ClusterSpec]
    shared_fixtures: tuple[str, ...]
    docs_only_prefixes: tuple[str, ...]
    agent_paths: tuple[str, ...]
    ci_script_paths: tuple[str, ...]
    pyproject_path: str


def _as_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


META_KEYS = frozenset(
    {
        "sharedFixtures",
        "docsOnlyPrefixes",
        "agentPaths",
        "ciScriptPaths",
        "pyprojectPath",
    }
)
FALLBACK_KEYS = frozenset({"tests"})
CLUSTER_KEYS = frozenset(
    {
        "production",
        "moduleTests",
        "clusterTests",
        "tests",
        "validators",
        "staticTargets",
        "allowNoMatch",
    }
)


def registry_schema_errors(data: dict[str, object]) -> list[str]:
    errors: list[str] = []
    meta = data.get("meta")
    if isinstance(meta, dict):
        for key in meta:
            if key not in META_KEYS:
                errors.append(
                    f"[TEST-IMPACT-SCHEMA-002] meta key: {key} remediation: remove or rename"
                )
    fallback = data.get("fallback")
    if isinstance(fallback, dict):
        for key in fallback:
            if key not in FALLBACK_KEYS:
                errors.append(
                    f"[TEST-IMPACT-SCHEMA-002] fallback key: {key} remediation: remove or rename"
                )
    clusters = data.get("clusters")
    if isinstance(clusters, dict):
        for cluster_name, section in clusters.items():
            if not isinstance(section, dict):
                continue
            for key in section:
                if key == "tests":
                    errors.append(
                        f"[TEST-IMPACT-SCHEMA-003] cluster: {cluster_name} key: tests "
                        "remediation: use moduleTests and clusterTests"
                    )
                    continue
                if key not in CLUSTER_KEYS:
                    remediation = "use staticTargets" if key == "static_targets" else "remove key"
                    errors.append(
                        f"[TEST-IMPACT-SCHEMA-002] cluster: {cluster_name} key: {key} "
                        f"remediation: {remediation}"
                    )
    return errors


def load_registry(path: Path) -> Registry:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    schema_errors = registry_schema_errors(data)
    if schema_errors:
        raise ValueError("\n".join(schema_errors))
    clusters: dict[str, ClusterSpec] = {}
    for name, section in data.get("clusters", {}).items():
        if not isinstance(section, dict):
            continue
        legacy_tests = _as_tuple(section.get("tests"))
        if legacy_tests:
            raise ValueError(
                f"[TEST-IMPACT-SCHEMA-003] cluster: {name} key: tests "
                "remediation: use moduleTests and clusterTests"
            )
        module_tests = _as_tuple(section.get("moduleTests"))
        cluster_tests = _as_tuple(section.get("clusterTests"))
        clusters[name] = ClusterSpec(
            name=name,
            production=_as_tuple(section.get("production")),
            module_tests=module_tests,
            cluster_tests=cluster_tests,
            validators=_as_tuple(section.get("validators")),
            static_targets=_as_tuple(section.get("staticTargets")),
            allow_no_match=bool(section.get("allowNoMatch", False)),
        )
    meta = data.get("meta", {})
    if not isinstance(meta, dict):
        meta = {}
    return Registry(
        clusters=clusters,
        shared_fixtures=_as_tuple(meta.get("sharedFixtures")),
        docs_only_prefixes=_as_tuple(meta.get("docsOnlyPrefixes")),
        agent_paths=_as_tuple(meta.get("agentPaths")),
        ci_script_paths=_as_tuple(meta.get("ciScriptPaths")),
        pyproject_path=str(meta.get("pyprojectPath", "pyproject.toml")),
    )


def path_matches(path: str, patterns: tuple[str, ...]) -> bool:
    normalized = path.replace("\\", "/")
    for pattern in patterns:
        if fnmatch.fnmatch(normalized, pattern):
            return True
        if normalized == pattern:
            return True
        if pattern.endswith("/") and normalized.startswith(pattern):
            return True
    return False


def is_docs_only(path: str, registry: Registry) -> bool:
    normalized = path.replace("\\", "/")
    return any(normalized.startswith(prefix) for prefix in registry.docs_only_prefixes)


def clusters_for_file(
    path: str,
    registry: Registry,
    *,
    dev_scope: bool = False,
) -> set[str]:
    normalized = path.replace("\\", "/")
    if normalized in registry.shared_fixtures or normalized == "tests/conftest.py":
        # L0/L1: avoid 100+ file fan-out; L2/registry validation still uses full set.
        if dev_scope:
            return {"test-selection"}
        return set(ALL_PYTEST_CLUSTERS)
    if normalized.startswith("tests/") and normalized.endswith(".py"):
        return {"_test_file"}
    matched: set[str] = set()
    if any(normalized.startswith(prefix) for prefix in registry.agent_paths):
        matched.add("agent-workflow")
    if any(normalized == item or normalized.startswith(item) for item in registry.ci_script_paths):
        matched.add("agent-workflow")
    if normalized == registry.pyproject_path:
        matched.add("packaging")
        # L2 keeps the agent-workflow coupling; L0/L1 stay packaging validators + unit slice.
        if not dev_scope:
            matched.add("agent-workflow")
    for cluster in registry.clusters.values():
        if path_matches(normalized, cluster.production):
            matched.add(cluster.name)
    if normalized.startswith("spell_sync/") and not matched:
        matched.add(CONSERVATIVE_FALLBACK_CLUSTER)
    return matched


def required_safety_clusters(
    changed_files: list[str],
    registry: Registry,
    *,
    dev_scope: bool = False,
) -> set[str]:
    required: set[str] = set()
    for path in changed_files:
        for cluster_name in clusters_for_file(path, registry, dev_scope=dev_scope):
            if cluster_name in SAFETY_CRITICAL_CLUSTERS:
                required.add(cluster_name)
    return required


def dedupe_sorted(items: set[str] | list[str]) -> list[str]:
    return sorted(set(items))
