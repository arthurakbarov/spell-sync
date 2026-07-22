"""Pytest: repository root on sys.path and shared fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from spell_sync.cli_options import CliOptions

pytest_plugins = ["conftest_execution"]


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "owner: owner-only tests requiring real HOME archive",
    )


@pytest.fixture(autouse=True)
def _isolated_test_environment(request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolate HOME, XDG roots, and uv cache for deterministic non-owner tests."""
    if request.node.get_closest_marker("owner"):
        yield None
        return
    home = tmp_path / "isolated-home"
    home.mkdir(parents=True, exist_ok=True)
    cache = tmp_path / "uv-cache"
    cache.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))
    monkeypatch.setenv("XDG_STATE_HOME", str(home / ".local" / "state"))
    monkeypatch.setenv("UV_CACHE_DIR", str(cache))
    yield home


@pytest.fixture
def isolated_test_home(_isolated_test_environment: Path | None) -> Path | None:
    """Isolated HOME directory when environment isolation is active."""
    return _isolated_test_environment

_ROOT = Path(__file__).resolve().parent.parent
_TESTS = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

DEFAULT_OPTS = CliOptions()
