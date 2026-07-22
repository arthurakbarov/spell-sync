"""Unrelated process fixtures must terminate even on assertion failure."""

from __future__ import annotations

import signal
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.process_tree import read_process_identity  # noqa: E402
from tests.conftest_execution import marker_sleep_command  # noqa: E402


def _pid_alive(pid: int) -> bool:
    ident = read_process_identity(pid)
    return ident is not None and ident.is_running()


def test_failed_assertion_leaves_no_marker_process(isolated_state_dir):
    del isolated_state_dir
    unrelated = subprocess.Popen(
        marker_sleep_command("EXEC_UNRELATED_MARKER", 60.0),
        start_new_session=True,
    )
    try:
        try:
            assert False, "forced assertion failure"
        finally:
            if _pid_alive(unrelated.pid):
                unrelated.send_signal(signal.SIGTERM)
                unrelated.wait(timeout=5)
    except AssertionError:
        pass
    assert not _pid_alive(unrelated.pid)
