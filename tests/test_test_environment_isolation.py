"""Autouse HOME/XDG/uv-cache isolation for non-owner pytest sessions."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_home_is_isolated_under_pytest_tmp_path(isolated_test_home: Path | None) -> None:
    assert isolated_test_home is not None
    assert os.environ["HOME"] == str(isolated_test_home)
    assert isolated_test_home.is_dir()
    assert isolated_test_home.name == "isolated-home"
    assert "pytest" in isolated_test_home.as_posix()


def test_xdg_and_uv_cache_dirs_are_isolated(isolated_test_home: Path | None) -> None:
    assert isolated_test_home is not None
    assert os.environ["XDG_CONFIG_HOME"] == str(isolated_test_home / ".config")
    assert os.environ["XDG_DATA_HOME"] == str(isolated_test_home / ".local" / "share")
    assert os.environ["XDG_STATE_HOME"] == str(isolated_test_home / ".local" / "state")
    assert os.environ["UV_CACHE_DIR"].startswith(str(isolated_test_home.parent))


def test_isolated_home_is_empty_at_test_start(isolated_test_home: Path | None) -> None:
    assert isolated_test_home is not None
    assert list(isolated_test_home.iterdir()) == []


@pytest.mark.owner
def test_owner_marker_preserves_real_home() -> None:
    assert os.environ["HOME"] == str(Path.home())
