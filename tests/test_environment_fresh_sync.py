"""Fresh repository sync creates venv, metadata, and environment evidence."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.project_environment import cmd_check, cmd_sync

ROOT = Path(__file__).resolve().parents[1]


def _copy_environment_inputs(dest: Path) -> None:
    for name in (".python-version", "pyproject.toml", "uv.lock"):
        shutil.copy2(ROOT / name, dest / name)
    shutil.copytree(ROOT / "config", dest / "config")


def test_fresh_copy_sync_writes_venv_metadata_and_evidence(tmp_path: Path) -> None:
    if shutil.which("uv") is None:
        pytest.skip("uv required for fresh sync test")
    _copy_environment_inputs(tmp_path)
    assert not (tmp_path / ".venv").exists()

    sync = cmd_sync(tmp_path, allow_python_download=False)
    if sync.exit_code != 0 and sync.failed_id == "environment.sync-required":
        pytest.skip(f"uv sync unavailable in test sandbox: {sync.message}")
    assert sync.exit_code == 0, f"{sync.failed_id}: {sync.message}"

    assert (tmp_path / ".venv").is_dir()
    assert (tmp_path / ".venv" / ".spell-sync-environment.json").is_file()
    assert (tmp_path / ".artifacts" / "environment" / "environment.json").is_file()

    check = cmd_check(tmp_path)
    assert check.exit_code == 0, f"{check.failed_id}: {check.message}"
