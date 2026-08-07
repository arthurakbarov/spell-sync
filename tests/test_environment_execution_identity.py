"""Execution identity binds uv.lock, manifest, and Python patch."""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

from scripts.environment_contract.contract import file_digest
from scripts.environment_contract.fingerprint import (
    EnvironmentFingerprint,
    build_environment_fingerprint_from_probe,
)
from scripts.environment_contract.manifest import (
    DistributionRecord,
    InstalledManifest,
    manifest_digest,
)
from scripts.environment_contract.probe import InterpreterProbe
from scripts.execution_control.identity import build_workload_payload, workload_fingerprint

ROOT = Path(__file__).resolve().parents[1]


def _base_probe(*, python_version: str = "3.14.6") -> InterpreterProbe:
    manifest = InstalledManifest(
        schema_version=1,
        distributions=(
            DistributionRecord(name="pytest", version="8.0.0", editable=False, source_type="index"),
        ),
    )
    return InterpreterProbe(
        python_implementation="cpython",
        python_version=python_version,
        python_cache_tag="cpython-312",
        executable_identity="exec-id",
        base_prefix_identity="base-id",
        pytest_version="8.0.0",
        installed_manifest=manifest,
    )


def _fingerprint_for_lock(
    root: Path, lock_bytes: bytes, *, python_version: str = "3.14.6"
) -> EnvironmentFingerprint:
    lock_path = root / "uv.lock"
    lock_path.write_bytes(lock_bytes)
    return build_environment_fingerprint_from_probe(
        root,
        _base_probe(python_version=python_version),
        uv_version="0.11.21",
    )


def test_workload_fingerprint_changes_when_uv_lock_digest_changes(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    for root in (first_root, second_root):
        root.mkdir()
        shutil.copy2(ROOT / "pyproject.toml", root / "pyproject.toml")
        shutil.copytree(ROOT / "config", root / "config")

    first = _fingerprint_for_lock(first_root, b"lock-a\n")
    second = _fingerprint_for_lock(second_root, b"lock-b\n")

    command = [str(ROOT / "scripts" / "ci_runner.py")]
    first_payload = build_workload_payload(
        root=first_root,
        execution_id="ci:full",
        command=command,
        mode="full",
        environment_signature=first.signature(),
    )
    second_payload = build_workload_payload(
        root=second_root,
        execution_id="ci:full",
        command=command,
        mode="full",
        environment_signature=second.signature(),
    )
    assert workload_fingerprint(
        execution_id="ci:full", workload=first_payload
    ) != workload_fingerprint(
        execution_id="ci:full",
        workload=second_payload,
    )
    assert first_payload["configDigests"]["uv.lock"] != second_payload["configDigests"]["uv.lock"]
    assert first.uv_lock_digest != second.uv_lock_digest


def test_signature_changes_when_installed_manifest_changes(tmp_path: Path) -> None:
    shutil.copy2(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    shutil.copy2(ROOT / "uv.lock", tmp_path / "uv.lock")
    shutil.copytree(ROOT / "config", tmp_path / "config")

    probe_a = _base_probe()
    probe_b = replace(
        probe_a,
        installed_manifest=InstalledManifest(
            schema_version=1,
            distributions=(
                DistributionRecord(
                    name="pytest", version="8.0.1", editable=False, source_type="index"
                ),
            ),
        ),
    )
    assert manifest_digest(probe_a.installed_manifest) != manifest_digest(
        probe_b.installed_manifest
    )

    fp_a = build_environment_fingerprint_from_probe(tmp_path, probe_a, uv_version="0.11.21")
    fp_b = build_environment_fingerprint_from_probe(tmp_path, probe_b, uv_version="0.11.21")
    assert fp_a.installed_environment_digest != fp_b.installed_environment_digest
    assert fp_a.signature() != fp_b.signature()


def test_python_patch_affects_environment_fingerprint(tmp_path: Path) -> None:
    shutil.copy2(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    shutil.copy2(ROOT / "uv.lock", tmp_path / "uv.lock")
    shutil.copytree(ROOT / "config", tmp_path / "config")

    patch_12 = build_environment_fingerprint_from_probe(
        tmp_path,
        _base_probe(python_version="3.14.6"),
        uv_version="0.11.21",
    )
    patch_12_other = build_environment_fingerprint_from_probe(
        tmp_path,
        _base_probe(python_version="3.14.7"),
        uv_version="0.11.21",
    )
    assert patch_12.python_version == "3.14.6"
    assert patch_12_other.python_version == "3.14.7"
    assert patch_12.signature() != patch_12_other.signature()
    assert (
        file_digest(tmp_path / "uv.lock")
        == patch_12.uv_lock_digest
        == patch_12_other.uv_lock_digest
    )
