"""Environment fingerprint for execution and CI evidence identity."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

from .contract import contract_digest, file_digest, load_contract
from .probe import InterpreterProbe, run_interpreter_probe, venv_python


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

    def to_summary_dict(self) -> dict[str, object]:
        return {
            "environmentFingerprint": self.signature(),
            "environmentContractDigest": self.environment_contract_digest,
            "pyprojectDigest": self.pyproject_digest,
            "uvLockDigest": self.uv_lock_digest,
            "installedEnvironmentDigest": self.installed_environment_digest,
            "pythonImplementation": self.python_implementation,
            "pythonVersion": self.python_version,
            "pythonCacheTag": self.python_cache_tag,
            "uvVersion": self.uv_version,
            "selectedDependencyGroups": list(self.selected_dependency_groups),
            "environmentStable": True,
        }


def build_environment_fingerprint_from_probe(
    root: Path,
    probe: InterpreterProbe,
    *,
    uv_version: str,
    selected_groups: tuple[str, ...] = ("dev",),
    offline_mode: bool = True,
) -> EnvironmentFingerprint:
    load_contract(root)
    lock_path = root / "uv.lock"
    return EnvironmentFingerprint(
        environment_contract_digest=contract_digest(root),
        pyproject_digest=file_digest(root / "pyproject.toml"),
        uv_lock_digest=file_digest(lock_path) if lock_path.is_file() else "",
        python_implementation=probe.python_implementation,
        python_version=probe.python_version,
        python_cache_tag=probe.python_cache_tag,
        uv_version=uv_version,
        pytest_version=probe.pytest_version,
        selected_dependency_groups=selected_groups,
        installed_environment_digest=probe.installed_environment_digest,
        offline_mode=offline_mode,
        platform_family=sys.platform,
        architecture=platform.machine(),
    )


def resolve_project_environment_fingerprint(
    root: Path,
    *,
    uv_version: str,
    selected_groups: tuple[str, ...] = ("dev",),
    offline_mode: bool = True,
) -> EnvironmentFingerprint | None:
    contract = load_contract(root)
    python = venv_python(root / contract.environment_directory)
    if python is None:
        return None
    probe = run_interpreter_probe(python, project_root=root)
    return build_environment_fingerprint_from_probe(
        root,
        probe,
        uv_version=uv_version,
        selected_groups=selected_groups,
        offline_mode=offline_mode,
    )


def build_environment_fingerprint(
    root: Path,
    *,
    uv_version: str,
    selected_groups: tuple[str, ...] = ("dev",),
    offline_mode: bool = True,
    manifest: object | None = None,
) -> EnvironmentFingerprint:
    del manifest
    resolved = resolve_project_environment_fingerprint(
        root,
        uv_version=uv_version,
        selected_groups=selected_groups,
        offline_mode=offline_mode,
    )
    if resolved is None:
        load_contract(root)
        lock_path = root / "uv.lock"
        return EnvironmentFingerprint(
            environment_contract_digest=contract_digest(root),
            pyproject_digest=file_digest(root / "pyproject.toml"),
            uv_lock_digest=file_digest(lock_path) if lock_path.is_file() else "",
            python_implementation="",
            python_version="",
            python_cache_tag="",
            uv_version=uv_version,
            pytest_version="",
            selected_dependency_groups=selected_groups,
            installed_environment_digest="",
            offline_mode=offline_mode,
            platform_family=sys.platform,
            architecture=platform.machine(),
        )
    return resolved
