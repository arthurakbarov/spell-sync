"""cmd_check detects metadata drift and manual manifest mutation."""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.environment_contract.metadata import (
    read_environment_metadata,
    write_environment_metadata,
)
from scripts.project_environment import cmd_check, cmd_sync

ROOT = Path(__file__).resolve().parents[1]


def _copy_environment_inputs(dest: Path) -> None:
    for name in (".python-version", "pyproject.toml", "uv.lock"):
        shutil.copy2(ROOT / name, dest / name)
    shutil.copytree(ROOT / "config", dest / "config")


@pytest.fixture(scope="module")
def synced_repo_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if shutil.which("uv") is None:
        pytest.skip("uv required for metadata validation tests")
    tmp_path = tmp_path_factory.mktemp("environment-metadata-template")
    _copy_environment_inputs(tmp_path)
    sync = cmd_sync(tmp_path, allow_python_download=False)
    if sync.exit_code != 0 and sync.failed_id == "environment.sync-required":
        pytest.skip(f"uv sync unavailable in test sandbox: {sync.message}")
    assert sync.exit_code == 0, f"{sync.failed_id}: {sync.message}"
    return tmp_path


@pytest.fixture
def synced_repo(synced_repo_template: Path, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    shutil.copytree(synced_repo_template, repo, symlinks=True)
    return repo


def _metadata_path(repo: Path) -> Path:
    return repo / ".venv" / ".spell-sync-environment.json"


def _mutate_metadata(repo: Path, **updates: object) -> None:
    path = _metadata_path(repo)
    metadata = read_environment_metadata(path)
    assert metadata is not None
    write_environment_metadata(path, replace(metadata, **updates))


def test_check_detects_pyproject_digest_drift(synced_repo: Path) -> None:
    _mutate_metadata(synced_repo, pyproject_digest="deadbeef" * 8)
    result = cmd_check(synced_repo)
    assert result.exit_code != 0
    assert result.failed_id == "environment.venv-stale"


def test_check_detects_uv_version_drift(synced_repo: Path) -> None:
    _mutate_metadata(synced_repo, uv_version="0.0.0")
    result = cmd_check(synced_repo)
    assert result.exit_code != 0
    assert result.failed_id == "environment.venv-stale"


def test_check_detects_selected_group_drift(synced_repo: Path) -> None:
    _mutate_metadata(synced_repo, selected_dependency_groups=("dev", "extra"))
    result = cmd_check(synced_repo)
    assert result.exit_code != 0
    assert result.failed_id == "environment.venv-stale"


def test_check_detects_manual_installed_manifest_mutation(synced_repo: Path) -> None:
    _mutate_metadata(synced_repo, installed_environment_digest="0" * 64)
    result = cmd_check(synced_repo)
    assert result.exit_code != 0
    assert result.failed_id == "environment.manual-mutation-detected"
