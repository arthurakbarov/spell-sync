"""Load and digest the committed environment contract."""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path

CONTRACT_REL_PATH = Path("config") / "environment-contract.toml"
CANONICAL_PYTHON = "3.12.13"


@dataclass(frozen=True, slots=True)
class EnvironmentContract:
    schema_version: int
    product_python_requirement: str
    maintainer_implementation: str
    canonical_python: str
    python_provider: str
    dependency_manager: str
    environment_directory: str
    normal_python_downloads: str
    bootstrap_python_downloads: str
    blocking_python: tuple[str, ...]
    experimental_python: tuple[str, ...]
    uv_required_version: str
    path: Path


def _as_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def load_contract(root: Path) -> EnvironmentContract:
    path = root / CONTRACT_REL_PATH
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    product = data.get("product", {})
    maintainer = data.get("maintainer", {})
    downloads = maintainer.get("pythonDownloads", {}) if isinstance(maintainer, dict) else {}
    compatibility = data.get("compatibility", {})
    toolchain = data.get("toolchain", {})
    if not isinstance(product, dict):
        product = {}
    if not isinstance(maintainer, dict):
        maintainer = {}
    if not isinstance(downloads, dict):
        downloads = {}
    if not isinstance(compatibility, dict):
        compatibility = {}
    if not isinstance(toolchain, dict):
        toolchain = {}
    return EnvironmentContract(
        schema_version=int(data.get("schemaVersion", 0)),
        product_python_requirement=str(product.get("pythonRequirement", "")),
        maintainer_implementation=str(maintainer.get("implementation", "")),
        canonical_python=str(maintainer.get("canonicalPython", "")),
        python_provider=str(maintainer.get("pythonProvider", "")),
        dependency_manager=str(maintainer.get("dependencyManager", "")),
        environment_directory=str(maintainer.get("environmentDirectory", ".venv")),
        normal_python_downloads=str(downloads.get("normalCommands", "")),
        bootstrap_python_downloads=str(downloads.get("bootstrapCommand", "")),
        blocking_python=_as_tuple(compatibility.get("blockingPython")),
        experimental_python=_as_tuple(compatibility.get("experimentalPython")),
        uv_required_version=str(toolchain.get("uvRequiredVersion", "")),
        path=path,
    )


def contract_digest(root: Path) -> str:
    path = root / CONTRACT_REL_PATH
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()
