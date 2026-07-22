"""Local .venv environment metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ENVIRONMENT_METADATA_REL = Path(".venv") / ".spell-sync-environment.json"


@dataclass(frozen=True, slots=True)
class EnvironmentMetadata:
    schema_version: int
    created_at: str
    python_implementation: str
    python_version: str
    python_cache_tag: str
    base_interpreter_identity: str
    uv_version: str
    environment_contract_digest: str
    pyproject_digest: str
    uv_lock_digest: str
    selected_dependency_groups: tuple[str, ...]
    installed_environment_digest: str

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": self.schema_version,
            "createdAt": self.created_at,
            "pythonImplementation": self.python_implementation,
            "pythonVersion": self.python_version,
            "pythonCacheTag": self.python_cache_tag,
            "baseInterpreterIdentity": self.base_interpreter_identity,
            "uvVersion": self.uv_version,
            "environmentContractDigest": self.environment_contract_digest,
            "pyprojectDigest": self.pyproject_digest,
            "uvLockDigest": self.uv_lock_digest,
            "selectedDependencyGroups": list(self.selected_dependency_groups),
            "installedEnvironmentDigest": self.installed_environment_digest,
        }


def write_environment_metadata(path: Path, metadata: EnvironmentMetadata) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(metadata.to_json_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def read_environment_metadata(path: Path) -> EnvironmentMetadata | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    groups = payload.get("selectedDependencyGroups", [])
    if not isinstance(groups, list):
        groups = []
    return EnvironmentMetadata(
        schema_version=int(payload.get("schemaVersion", 0)),
        created_at=str(payload.get("createdAt", "")),
        python_implementation=str(payload.get("pythonImplementation", "")),
        python_version=str(payload.get("pythonVersion", "")),
        python_cache_tag=str(payload.get("pythonCacheTag", "")),
        base_interpreter_identity=str(payload.get("baseInterpreterIdentity", "")),
        uv_version=str(payload.get("uvVersion", "")),
        environment_contract_digest=str(payload.get("environmentContractDigest", "")),
        pyproject_digest=str(payload.get("pyprojectDigest", "")),
        uv_lock_digest=str(payload.get("uvLockDigest", "")),
        selected_dependency_groups=tuple(str(item) for item in groups),
        installed_environment_digest=str(payload.get("installedEnvironmentDigest", "")),
    )


def metadata_now() -> str:
    return datetime.now(timezone.utc).isoformat()
