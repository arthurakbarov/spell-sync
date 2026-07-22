"""Production-path hard timeout detached descendant cleanup."""

from __future__ import annotations

import signal
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.process_tree import (  # noqa: E402
    read_process_identity,
    run_owned_command,
)
from tests.conftest_execution import marker_sleep_command  # noqa: E402


def _pid_alive(pid: int) -> bool:
    ident = read_process_identity(pid)
    if ident is None:
        return False
    return ident.is_running()


def test_hard_timeout_removes_detached_descendants_via_run_owned_command(
    isolated_state_dir, tmp_path
):
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
    result = run_owned_command(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=None,
        hard_seconds=0.35,
        soft_seconds=0.2,
        stall_seconds=None,
        termination_grace_seconds=0.25,
        tracker=None,
        enforce_hard=True,
        enforce_stall=False,
    )

    assert result.exit_code == 124
    assert child_pid_file.is_file()
    assert grandchild_pid_file.is_file()
    child_pid = int(child_pid_file.read_text(encoding="utf-8"))
    grandchild_pid = int(grandchild_pid_file.read_text(encoding="utf-8"))
    assert result.timed_out is True
    assert result.detached_pids == ()
    assert not _pid_alive(child_pid)
    assert not _pid_alive(grandchild_pid)
    assert _pid_alive(unrelated.pid)
    unrelated.send_signal(signal.SIGTERM)
    unrelated.wait(timeout=5)
