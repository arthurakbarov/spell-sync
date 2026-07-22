"""Descendant cleanup via production run_owned_command path."""

from __future__ import annotations

import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.process_tree import (  # noqa: E402
    capture_ownership_snapshot,
    read_process_identity,
    run_owned_command,
    terminate_ownership_snapshot,
)
from tests.conftest_execution import marker_sleep_command  # noqa: E402


def _pid_alive(pid: int) -> bool:
    ident = read_process_identity(pid)
    if ident is None:
        return False
    return ident.is_running()


def _wait_for_file(path: Path, *, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return
        time.sleep(0.02)
    raise AssertionError(f"missing readiness file: {path}")


def test_ownership_snapshot_captured_before_signals(isolated_state_dir):
    del isolated_state_dir
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        start_new_session=True,
    )
    time.sleep(0.05)
    snapshot = capture_ownership_snapshot(proc.pid, proc.pid)
    survivors = terminate_ownership_snapshot(snapshot, grace=0.15)
    proc.wait(timeout=5)
    assert not _pid_alive(proc.pid)
    assert not survivors or not any(_pid_alive(pid) for pid in survivors)


def test_term_ignoring_same_group_child_killed(isolated_state_dir):
    del isolated_state_dir
    script = textwrap.dedent(
        """
        import os, signal, subprocess, sys, time
        child = subprocess.Popen(
            [sys.executable, "-c",
             "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)"],
            start_new_session=False,
        )
        os.kill(os.getpid(), signal.SIGTERM)
        time.sleep(0.2)
        """
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        start_new_session=True,
    )
    time.sleep(0.15)
    snapshot = capture_ownership_snapshot(proc.pid, proc.pid)
    survivors = terminate_ownership_snapshot(snapshot, grace=0.15)
    proc.wait(timeout=5)
    assert not _pid_alive(proc.pid)
    assert not survivors or not any(_pid_alive(pid) for pid in survivors)


def test_detached_descendants_terminated(isolated_state_dir, tmp_path):
    del isolated_state_dir
    unrelated = subprocess.Popen(
        marker_sleep_command("EXEC_UNRELATED_MARKER", 60.0),
        start_new_session=True,
    )
    ready_file = tmp_path / "ready"
    child_pid_file = tmp_path / "child.pid"
    grandchild_pid_file = tmp_path / "grandchild.pid"
    script = textwrap.dedent(
        f"""
        import subprocess, sys, time
        from pathlib import Path
        grand = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            start_new_session=True,
        )
        Path({str(grandchild_pid_file)!r}).write_text(str(grand.pid))
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            start_new_session=True,
        )
        Path({str(child_pid_file)!r}).write_text(str(child.pid))
        Path({str(ready_file)!r}).write_text("READY")
        time.sleep(60)
        """
    )
    try:
        result = run_owned_command(
            [sys.executable, "-c", script],
            cwd=ROOT,
            env=None,
            hard_seconds=2.0,
            soft_seconds=0.5,
            stall_seconds=None,
            termination_grace_seconds=0.25,
            tracker=None,
            enforce_hard=True,
            enforce_stall=False,
        )
        _wait_for_file(ready_file, timeout=5.0)
        assert result.exit_code == 124
        assert child_pid_file.is_file()
        assert grandchild_pid_file.is_file()
        child_pid = int(child_pid_file.read_text(encoding="utf-8"))
        grandchild_pid = int(grandchild_pid_file.read_text(encoding="utf-8"))
        assert result.detached_pids == ()
        assert not _pid_alive(child_pid)
        assert not _pid_alive(grandchild_pid)
    finally:
        if _pid_alive(unrelated.pid):
            unrelated.send_signal(signal.SIGTERM)
            unrelated.wait(timeout=5)
    assert not _pid_alive(unrelated.pid)
