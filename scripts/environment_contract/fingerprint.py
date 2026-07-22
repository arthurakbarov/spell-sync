"""Environment fingerprint for execution and CI evidence identity."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

from .contract import contract_digest, file_digest, load_contract
from .manifest import (
    InstalledManifest,
    build_installed_manifest,
    current_python_cache_tag,
    manifest_digest,
)


@dataclass(frozen=True, slots=True)
class EnvironmentFingerprint:
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
    offline_mode: bool
    platform_family: str
    architecture: str

    def signature(self) -> str:
        payload = {
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
            "offlineMode": self.offline_mode,
            "platformFamily": self.platform_family,
            "architecture": self.architecture,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def _pytest_version() -> str:
    try:
        import pytest
    except ImportError:
        return ""
    return getattr(pytest, "__version__", "")


def build_environment_fingerprint(
    root: Path,
    *,
    uv_version: str,
    selected_groups: tuple[str, ...] = ("dev",),
    offline_mode: bool = True,
    manifest: InstalledManifest | None = None,
) -> EnvironmentFingerprint:
    load_contract(root)
    lock_path = root / "uv.lock"
    pyproject_path = root / "pyproject.toml"
    if manifest is None:
        manifest = build_installed_manifest(project_root=root)
    return EnvironmentFingerprint(
        environment_contract_digest=contract_digest(root),
        pyproject_digest=file_digest(pyproject_path),
        uv_lock_digest=file_digest(lock_path) if lock_path.is_file() else "",
        python_implementation=platform.python_implementation().lower(),
        python_version=platform.python_version(),
        python_cache_tag=current_python_cache_tag(),
        uv_version=uv_version,
        pytest_version=_pytest_version(),
        selected_dependency_groups=selected_groups,
        installed_environment_digest=manifest_digest(manifest),
        offline_mode=offline_mode,
        platform_family=sys.platform,
        architecture=platform.machine(),
    )
