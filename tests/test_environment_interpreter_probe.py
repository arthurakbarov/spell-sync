"""Interpreter probe reports venv Python, not ambient runtime."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.environment_contract.contract import CANONICAL_PYTHON, contract_digest, file_digest
from scripts.environment_contract.metadata import (
    EnvironmentMetadata,
    metadata_now,
)
from scripts.environment_contract.probe import run_interpreter_probe, venv_python

ROOT = Path(__file__).resolve().parents[1]


def _uv_version() -> str:
    proc = subprocess.run(["uv", "--version"], capture_output=True, text=True, check=False)
    match = re.search(r"uv\s+(\d+\.\d+\.\d+)", proc.stdout)
    return match.group(1) if match else ""


def test_interpreter_probe_reports_canonical_python_from_venv() -> None:
    venv_dir = ROOT / ".venv"
    venv_py = venv_python(venv_dir)
    if venv_py is None:
        pytest.skip("maintainer .venv required for interpreter probe test")

    probe = run_interpreter_probe(venv_py, project_root=ROOT)
    assert probe.python_version == CANONICAL_PYTHON


def test_metadata_from_probe_uses_venv_python_not_ambient() -> None:
    venv_dir = ROOT / ".venv"
    venv_py = venv_python(venv_dir)
    if venv_py is None:
        pytest.skip("maintainer .venv required for metadata probe test")
    if sys.version.split()[0] == CANONICAL_PYTHON:
        pytest.skip("ambient Python matches venv; cannot distinguish from sys.version")

    probe = run_interpreter_probe(venv_py, project_root=ROOT)
    metadata = EnvironmentMetadata(
        schema_version=1,
        created_at=metadata_now(),
        python_implementation=probe.python_implementation,
        python_version=probe.python_version,
        python_cache_tag=probe.python_cache_tag,
        base_interpreter_identity=probe.base_prefix_identity,
        uv_version=_uv_version(),
        environment_contract_digest=contract_digest(ROOT),
        pyproject_digest=file_digest(ROOT / "pyproject.toml"),
        uv_lock_digest=file_digest(ROOT / "uv.lock"),
        selected_dependency_groups=("dev",),
        installed_environment_digest=probe.installed_environment_digest,
    )
    payload = json.dumps(metadata.to_json_dict())

    assert CANONICAL_PYTHON in payload
    assert sys.version.split()[0] not in payload
    assert metadata.python_version == CANONICAL_PYTHON
    assert metadata.installed_environment_digest == probe.installed_environment_digest


def test_probe_ignores_project_root_build_egg_info() -> None:
    venv_dir = ROOT / ".venv"
    venv_py = venv_python(venv_dir)
    if venv_py is None:
        pytest.skip("maintainer .venv required for build-artifact probe test")

    before = run_interpreter_probe(venv_py, project_root=ROOT)
    egg_info = ROOT / "spell_sync.egg-info"
    egg_info.mkdir(exist_ok=True)
    (egg_info / "PKG-INFO").write_text(
        "Metadata-Version: 2.1\nName: spell-sync\nVersion: 0.0.0\n",
        encoding="utf-8",
    )
    try:
        after = run_interpreter_probe(venv_py, project_root=ROOT)
    finally:
        import shutil

        shutil.rmtree(egg_info, ignore_errors=True)

    assert after.installed_environment_digest == before.installed_environment_digest
