"""Shared environment contract utilities for spell-sync tooling."""

from .contract import (
    CANONICAL_PYTHON,
    CONTRACT_REL_PATH,
    EnvironmentContract,
    contract_digest,
    load_contract,
)
from .evidence import EnvironmentEvidence, read_environment_evidence, write_environment_evidence
from .fingerprint import (
    EnvironmentFingerprint,
    build_environment_fingerprint,
    build_environment_fingerprint_from_probe,
    resolve_project_environment_fingerprint,
)
from .manifest import InstalledManifest, build_installed_manifest, manifest_digest
from .metadata import (
    ENVIRONMENT_METADATA_REL,
    EnvironmentMetadata,
    read_environment_metadata,
    write_environment_metadata,
)
from .paths import EnvironmentPaths, production_environment_paths, test_environment_paths
from .probe import InterpreterProbe, run_interpreter_probe, venv_python

__all__ = [
    "CANONICAL_PYTHON",
    "CONTRACT_REL_PATH",
    "ENVIRONMENT_METADATA_REL",
    "EnvironmentContract",
    "EnvironmentEvidence",
    "EnvironmentFingerprint",
    "EnvironmentMetadata",
    "EnvironmentPaths",
    "InstalledManifest",
    "InterpreterProbe",
    "build_environment_fingerprint",
    "build_environment_fingerprint_from_probe",
    "build_installed_manifest",
    "contract_digest",
    "load_contract",
    "manifest_digest",
    "production_environment_paths",
    "read_environment_evidence",
    "read_environment_metadata",
    "resolve_project_environment_fingerprint",
    "run_interpreter_probe",
    "test_environment_paths",
    "venv_python",
    "write_environment_evidence",
    "write_environment_metadata",
]
