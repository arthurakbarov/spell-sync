"""Environment evidence read/write helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .fingerprint import EnvironmentFingerprint
from .paths import EnvironmentPaths, production_environment_paths


@dataclass(frozen=True, slots=True)
class EnvironmentEvidence:
    schema_version: int
    repository_head: str
    environment_contract_digest: str
    pyproject_digest: str
    uv_lock_digest: str
    python_implementation: str
    python_version: str
    python_cache_tag: str
    uv_version: str
    pytest_version: str
    selected_dependency_groups: tuple[str, ...]
    installed_environment_digest: str
    environment_check_exit: int
    lock_check_exit: int
    environment_fingerprint: str

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": self.schema_version,
            "repositoryHead": self.repository_head,
            "environmentContractDigest": self.environment_contract_digest,
            "pyprojectDigest": self.pyproject_digest,
            "uvLockDigest": self.uv_lock_digest,
            "pythonImplementation": self.python_implementation,
            "pythonVersion": self.python_version,
            "pythonCacheTag": self.python_cache_tag,
            "uvVersion": self.uv_version,
            "pytestVersion": self.pytest_version,
            "selectedDependencyGroups": list(self.selected_dependency_groups),
            "installedEnvironmentDigest": self.installed_environment_digest,
            "environmentCheckExit": self.environment_check_exit,
            "lockCheckExit": self.lock_check_exit,
            "environmentFingerprint": self.environment_fingerprint,
        }


def write_environment_evidence(
    root: Path,
    *,
    fingerprint: EnvironmentFingerprint,
    repository_head: str,
    check_exit: int,
    lock_exit: int,
    paths: EnvironmentPaths | None = None,
) -> Path:
    env_paths = paths or production_environment_paths(root)
    payload = EnvironmentEvidence(
        schema_version=1,
        repository_head=repository_head,
        environment_contract_digest=fingerprint.environment_contract_digest,
        pyproject_digest=fingerprint.pyproject_digest,
        uv_lock_digest=fingerprint.uv_lock_digest,
        python_implementation=fingerprint.python_implementation,
        python_version=fingerprint.python_version,
        python_cache_tag=fingerprint.python_cache_tag,
        uv_version=fingerprint.uv_version,
        pytest_version=fingerprint.pytest_version,
        selected_dependency_groups=fingerprint.selected_dependency_groups,
        installed_environment_digest=fingerprint.installed_environment_digest,
        environment_check_exit=check_exit,
        lock_check_exit=lock_exit,
        environment_fingerprint=fingerprint.signature(),
    )
    out = env_paths.environment_evidence_path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload.to_json_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return out


def read_environment_evidence(
    root: Path,
    *,
    paths: EnvironmentPaths | None = None,
) -> EnvironmentEvidence | None:
    env_paths = paths or production_environment_paths(root)
    path = env_paths.environment_evidence_path
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    groups = payload.get("selectedDependencyGroups", [])
    if not isinstance(groups, list):
        groups = []
    return EnvironmentEvidence(
        schema_version=int(payload.get("schemaVersion", 0)),
        repository_head=str(payload.get("repositoryHead", "")),
        environment_contract_digest=str(payload.get("environmentContractDigest", "")),
        pyproject_digest=str(payload.get("pyprojectDigest", "")),
        uv_lock_digest=str(payload.get("uvLockDigest", "")),
        python_implementation=str(payload.get("pythonImplementation", "")),
        python_version=str(payload.get("pythonVersion", "")),
        python_cache_tag=str(payload.get("pythonCacheTag", "")),
        uv_version=str(payload.get("uvVersion", "")),
        pytest_version=str(payload.get("pytestVersion", "")),
        selected_dependency_groups=tuple(str(item) for item in groups),
        installed_environment_digest=str(payload.get("installedEnvironmentDigest", "")),
        environment_check_exit=int(payload.get("environmentCheckExit", 1)),
        lock_check_exit=int(payload.get("lockCheckExit", 1)),
        environment_fingerprint=str(payload.get("environmentFingerprint", "")),
    )
