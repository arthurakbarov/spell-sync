"""Workload and policy fingerprints for execution control."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from .registry import ExecutionBudgetRegistry, registry_digest

_PACKAGE_ROOT = Path(__file__).resolve().parent

POLICY_SOURCE_FILES = (
    "controller.py",
    "progress.py",
    "process_tree.py",
    "diagnostics.py",
    "prediction.py",
    "registry.py",
    "mappings.py",
)

FORMULA_SCHEMA_VERSION = 1


def _hash_payload(payload: dict[str, Any]) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _file_content_digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize_command_token(token: str) -> str:
    path = Path(token)
    if path.is_absolute():
        return path.name
    return token


def _command_identity(command: list[str]) -> dict[str, Any]:
    normalized = [_normalize_command_token(part) for part in command]
    targets: list[str] = []
    module = ""
    if "-m" in command:
        index = command.index("-m")
        if index + 1 < len(command):
            module = _normalize_command_token(command[index + 1])
    for part in command:
        token = _normalize_command_token(part)
        if token.endswith(".py") or token.startswith("tests/"):
            targets.append(token)
    script_bytes_digest = ""
    script_path = ""
    if command:
        candidate = Path(command[0])
        if candidate.suffix == ".py" and candidate.is_file():
            script_path = candidate.name
            script_bytes_digest = _file_content_digest(candidate) or ""
        elif len(command) > 1:
            second = Path(command[1])
            if second.suffix == ".py" and second.is_file():
                script_path = second.name
                script_bytes_digest = _file_content_digest(second) or ""
    return {
        "argv": normalized,
        "module": module,
        "targets": sorted(set(targets)),
        "scriptPath": script_path,
        "scriptBytesDigest": script_bytes_digest,
    }


def _runner_module_digests(root: Path, command: list[str]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for rel in (
        "scripts/ci_runner.py",
        "scripts/run_focused_tests.py",
        "scripts/run_pre_final_checks.py",
        "scripts/test_plan.py",
        "scripts/run_snapshot_tests.py",
    ):
        path = root / rel
        digest = _file_content_digest(path)
        if digest:
            digests[rel] = digest
    if "-m" in command:
        index = command.index("-m")
        if index + 1 < len(command):
            module_name = command[index + 1]
            if module_name == "pytest":
                digests["pytest"] = "pytest"
            elif module_name == "spell_sync":
                pkg_init = root / "spell_sync" / "__init__.py"
                digest = _file_content_digest(pkg_init)
                if digest:
                    digests["spell_sync"] = digest
    return digests


def workload_fingerprint(*, execution_id: str, workload: dict[str, Any]) -> str:
    payload = {
        "executionId": execution_id,
        "workload": workload,
    }
    return _hash_payload(payload)


def policy_fingerprint(registry: ExecutionBudgetRegistry, profile_id: str) -> str:
    profile = registry.profiles[profile_id]
    module_digests = {
        name: _file_content_digest(_PACKAGE_ROOT / name) or "missing"
        for name in POLICY_SOURCE_FILES
    }
    payload = {
        "registryDigest": registry_digest(registry),
        "schemaVersion": registry.schema_version,
        "formulaSchemaVersion": FORMULA_SCHEMA_VERSION,
        "profileId": profile_id,
        "executionId": profile.execution_id,
        "progressContract": profile.progress_contract,
        "hardCapSeconds": profile.hard_cap_seconds,
        "moduleDigests": module_digests,
    }
    return _hash_payload(payload)


def normalized_signature(
    *,
    execution_id: str,
    workload_fingerprint_value: str,
    context_signature: str,
) -> str:
    payload = {
        "executionId": execution_id,
        "workloadFingerprint": workload_fingerprint_value,
        "contextSignature": context_signature,
    }
    return _hash_payload(payload)[:32]


def build_workload_payload(
    *,
    root: Path,
    execution_id: str,
    command: list[str],
    mode: str,
    test_file_count: int = 0,
    test_node_count: int = 0,
    cluster_ids: tuple[str, ...] = (),
    coverage: bool = False,
    tui: bool = False,
    packaging: bool = False,
) -> dict[str, Any]:
    major, minor = sys.version_info.major, sys.version_info.minor
    command_identity = _command_identity(command)
    config_digests: dict[str, str] = {}
    for rel in (
        "tests/execution-budget.toml",
        "pyproject.toml",
    ):
        path = root / rel
        digest = _file_content_digest(path)
        if digest:
            config_digests[rel] = digest
    return {
        "mode": mode,
        "executionId": execution_id,
        "command": command_identity,
        "runnerModules": _runner_module_digests(root, command),
        "testFileCount": test_file_count,
        "testNodeCount": test_node_count,
        "clusterIds": list(cluster_ids),
        "coverage": coverage,
        "tui": tui,
        "packaging": packaging,
        "pythonVersion": f"{major}.{minor}",
        "configDigests": config_digests,
        "rootMarker": "spell-sync",
    }
