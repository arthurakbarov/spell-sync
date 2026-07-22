"""Descendant cleanup and detached-process policy tests."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.process_tree import (  # noqa: E402
    _terminate_owned_group,
    terminate_descendants,
)
from tests.conftest_execution import marker_sleep_command  # noqa: E402


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


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
    pgid = proc.pid
    time.sleep(0.15)
    survivors = _terminate_owned_group(pgid, grace=0.15, root_pid=proc.pid)
    proc.wait(timeout=5)
    assert not _pid_alive(proc.pid)
    assert not survivors or not any(_pid_alive(pid) for pid in survivors)


def test_detached_descendants_terminated(isolated_state_dir, tmp_path):
    del isolated_state_dir
    unrelated = subprocess.Popen(
        marker_sleep_command("EXEC_UNRELATED_MARKER", 60.0),
        start_new_session=True,
    )
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
        time.sleep(60)
        """
    )
    runner = subprocess.Popen([sys.executable, "-c", script], start_new_session=True)
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if child_pid_file.is_file() and grandchild_pid_file.is_file():
            break
        time.sleep(0.05)
    child_pid = int(child_pid_file.read_text(encoding="utf-8"))
    grandchild_pid = int(grandchild_pid_file.read_text(encoding="utf-8"))
    terminate_descendants(runner.pid, grace=0.2)
    _terminate_owned_group(runner.pid, grace=0.2, root_pid=runner.pid)
    runner.wait(timeout=5)
    assert not _pid_alive(child_pid)
    assert not _pid_alive(grandchild_pid)
    assert _pid_alive(unrelated.pid)
    unrelated.send_signal(signal.SIGTERM)
    unrelated.wait(timeout=5)
