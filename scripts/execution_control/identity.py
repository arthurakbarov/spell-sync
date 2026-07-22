"""Workload and policy fingerprints for execution control."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .registry import ExecutionBudgetRegistry, registry_digest


def _hash_payload(payload: dict[str, Any]) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def workload_fingerprint(*, execution_id: str, workload: dict[str, Any]) -> str:
    payload = {
        "executionId": execution_id,
        "workload": workload,
    }
    return _hash_payload(payload)


def policy_fingerprint(registry: ExecutionBudgetRegistry, profile_id: str) -> str:
    profile = registry.profiles[profile_id]
    payload = {
        "registryDigest": registry_digest(registry),
        "schemaVersion": registry.schema_version,
        "profileId": profile_id,
        "executionId": profile.execution_id,
        "progressContract": profile.progress_contract,
        "hardCapSeconds": profile.hard_cap_seconds,
        "controllerSchemaVersion": 1,
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
    script = command[0] if command else ""
    if len(command) > 1 and command[0].endswith("python") or "python" in Path(script).name:
        script = command[1] if len(command) > 1 else script
    return {
        "mode": mode,
        "script": Path(script).name if script else "",
        "testFileCount": test_file_count,
        "testNodeCount": test_node_count,
        "clusterIds": list(cluster_ids),
        "coverage": coverage,
        "tui": tui,
        "packaging": packaging,
        "rootMarker": "spell-sync",
    }
