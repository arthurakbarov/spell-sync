"""Shared fixtures and helpers for execution-control tests."""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execution_control.history import HistoryStore  # noqa: E402
from scripts.execution_control.models import SpanRecord  # noqa: E402
from scripts.execution_control.registry import REGISTRY_REL_PATH, load_registry  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_execution_state(tmp_path, monkeypatch):
    """Keep execution-control state and session warnings out of real XDG_STATE_HOME."""
    state_home = tmp_path / "xdg-state"
    state_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_STATE_HOME", str(state_home))
    return state_home


@pytest.fixture
def isolated_state_dir(_isolated_execution_state):
    """Redirect XDG_STATE_HOME to an isolated temp directory."""
    return _isolated_execution_state


@pytest.fixture
def registry():
    """Load the test execution budget registry."""
    return load_registry(ROOT / REGISTRY_REL_PATH)


@pytest.fixture
def history_store(isolated_state_dir):
    """Open a fresh HistoryStore backed by isolated SQLite."""
    del isolated_state_dir
    return HistoryStore.open()


@pytest.fixture
def history(history_store):
    """Alias for history_store."""
    return history_store


def sleep_command(seconds: float) -> list[str]:
    """Return a command that sleeps for the given duration."""
    return [
        sys.executable,
        "-c",
        f"import time; time.sleep({seconds})",
    ]


def exit_command(code: int) -> list[str]:
    """Return a command that exits with the given code."""
    return [sys.executable, "-c", f"import sys; sys.exit({code})"]


def echo_command(*lines: str) -> list[str]:
    """Return a command that prints lines to stdout."""
    body = "; ".join(f"print({line!r})" for line in lines)
    return [sys.executable, "-c", body]


def spam_command(seconds: float, line: str = "noise") -> list[str]:
    """Return a command that repeatedly prints the same line while sleeping."""
    return [
        sys.executable,
        "-c",
        (
            "import sys, time\n"
            f"deadline=time.monotonic()+{seconds}\n"
            f"line={line!r}\n"
            "while time.monotonic() < deadline:\n"
            "    print(line, flush=True)\n"
            "    time.sleep(0.01)\n"
        ),
    ]


def spawn_tree_command(leaf_sleep: float = 5.0, root_sleep: float = 5.0) -> list[str]:
    """Return a command that spawns a child which spawns a grandchild."""
    script = f"""
import subprocess, sys, time
grand = [sys.executable, "-c", "import time; time.sleep({leaf_sleep})"]
child = [sys.executable, "-c",
         "import subprocess, sys, time; "
         "subprocess.Popen(" + repr(grand) + ", start_new_session=True); "
         "time.sleep({leaf_sleep})"]
subprocess.Popen(child, start_new_session=True)
time.sleep({root_sleep})
"""
    return [sys.executable, "-c", script]


def grandchild_command(seconds: float) -> list[str]:
    """Return a command that spawns a grandchild sleep process."""
    return [
        sys.executable,
        "-c",
        (
            "import subprocess, sys, time\n"
            f"subprocess.Popen([sys.executable, '-c', 'import time; time.sleep({seconds})'])\n"
            f"time.sleep({seconds})\n"
        ),
    ]


def marker_sleep_command(marker: str, seconds: float) -> list[str]:
    """Sleep command tagged with a unique marker for orphan detection."""
    return [
        sys.executable,
        "-c",
        f"import time; print({marker!r}); time.sleep({seconds})",
    ]


def make_span_record(**overrides) -> SpanRecord:
    """Build a minimal SpanRecord with sensible defaults."""
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    defaults = {
        "run_id": "run-test-001",
        "span_id": "span-test-001",
        "parent_span_id": None,
        "execution_id": "gate:focused-module",
        "profile_id": "focused-module",
        "normalized_signature": "sig" * 8,
        "workload_fingerprint": "workload" * 8,
        "policy_fingerprint": "policy" * 8,
        "start_time": now,
        "end_time": now,
        "duration_seconds": 1.0,
        "exit_code": 0,
        "status": "success",
        "expected_seconds": 45.0,
        "soft_seconds": 90.0,
        "stall_seconds": None,
        "hard_seconds": 180.0,
        "prediction_source": "registry-default",
        "confidence": "none",
        "sample_count": 0,
        "progress_event_count": 0,
        "maximum_progress_gap": 0.0,
        "active_child_at_end": None,
        "accepted_for_learning": True,
        "quarantine_reason": None,
        "diagnostic_bundle": None,
    }
    defaults.update(overrides)
    return SpanRecord(**defaults)


def sqlite_preflight_probe(database: Path) -> None:
    """Verify SQLite WAL mode and basic read/write on a database file."""
    connection = sqlite3.connect(database, timeout=5)
    try:
        connection.execute("PRAGMA busy_timeout=5000")
        journal_mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        connection.execute("CREATE TABLE preflight (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO preflight(value) VALUES (?)", ("ok",))
        connection.commit()
        value = connection.execute("SELECT value FROM preflight").fetchone()[0]
        assert value == "ok"
        assert journal_mode.lower() == "wal"
    finally:
        connection.close()
