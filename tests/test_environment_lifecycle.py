"""Project environment lifecycle: info, check, and venv presence contracts."""

from __future__ import annotations

import io
import shutil
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from scripts.project_environment import cmd_check, cmd_info, cmd_sync

ROOT = Path(__file__).resolve().parents[1]


def _copy_environment_inputs(dest: Path) -> None:
    for name in (".python-version", "pyproject.toml", "uv.lock"):
        shutil.copy2(ROOT / name, dest / name)
    shutil.copytree(ROOT / "config", dest / "config")


def test_info_reports_synced_environment_fields() -> None:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exit_code = cmd_info(ROOT, json_output=False)
    output = buffer.getvalue()
    assert exit_code == 0
    assert "ENVIRONMENT_RESULT=success" in output
    assert "venvPresent=True" in output
    assert "metadataPresent=True" in output
    assert "pythonVersionFile=3.12.13" in output
    assert "uvVersion=0.11.21" in output


def test_check_passes_after_synced_repository() -> None:
    venv_dir = ROOT / ".venv"
    metadata = venv_dir / ".spell-sync-environment.json"
    if not venv_dir.is_dir() or not metadata.is_file():
        pytest.skip("maintainer .venv with environment metadata required for lifecycle check")
    result = cmd_check(ROOT)
    assert result.exit_code == 0, f"{result.failed_id}: {result.message}"


def test_check_fails_when_venv_missing(tmp_path: Path) -> None:
    _copy_environment_inputs(tmp_path)
    result = cmd_check(tmp_path)
    assert result.exit_code != 0
    assert result.failed_id == "environment.venv-missing"


def test_sync_writes_metadata_and_check_succeeds(tmp_path: Path) -> None:
    if shutil.which("uv") is None:
        pytest.skip("uv required for sync lifecycle test")
    _copy_environment_inputs(tmp_path)
    sync = cmd_sync(tmp_path, allow_python_download=False)
    if sync.exit_code != 0 and sync.failed_id == "environment.sync-required":
        pytest.skip(f"uv sync unavailable in test sandbox: {sync.message}")
    assert sync.exit_code == 0, f"{sync.failed_id}: {sync.message}"
    metadata = tmp_path / ".venv" / ".spell-sync-environment.json"
    assert metadata.is_file()
    check = cmd_check(tmp_path)
    assert check.exit_code == 0, f"{check.failed_id}: {check.message}"
