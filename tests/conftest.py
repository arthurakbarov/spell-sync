"""Pytest: repository root on sys.path and shared fixtures."""

import sys
from pathlib import Path

import pytest

from spell_sync.cli_options import CliOptions


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "real_home: tests that intentionally use the real HOME directory",
    )


@pytest.fixture(autouse=True)
def _isolated_test_environment(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Isolate HOME, XDG roots, and uv cache unless ``real_home`` is marked."""
    if request.node.get_closest_marker("real_home"):
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
    """Alias for the autouse HOME isolation root (when isolation is active)."""
    return _isolated_test_environment


@pytest.fixture
def history_record_cap(monkeypatch: pytest.MonkeyPatch) -> int:
    """Small MAX_HISTORY_RECORDS for compaction tests (avoid 500-row setups)."""
    from tests.history_test_utils import install_history_record_cap

    return install_history_record_cap(monkeypatch)


_ROOT = Path(__file__).resolve().parent.parent
_TESTS = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

DEFAULT_OPTS = CliOptions()
