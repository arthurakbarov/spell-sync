"""Parent interrupt lifecycle with readiness handshake."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_for_markers(proc: subprocess.Popen[str], markers: tuple[str, ...], timeout: float) -> str:
    output = ""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        chunk = proc.stdout.readline() if proc.stdout else ""
        if chunk:
            output += chunk
            if all(marker in output for marker in markers):
                return output
        elif proc.poll() is not None:
            break
        time.sleep(0.02)
    raise AssertionError(f"missing readiness markers in output: {output!r}")


def test_sigint_terminates_owned_tree_and_preserves_unrelated(isolated_state_dir, tmp_path):
    del isolated_state_dir
    child_pid_file = tmp_path / "child.pid"
    grandchild_pid_file = tmp_path / "grandchild.pid"
    unrelated = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        start_new_session=True,
    )
    owned_script = textwrap.dedent(
        f"""
        import subprocess, sys, time
        from pathlib import Path
        grand = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            start_new_session=True,
        )
        Path({str(grandchild_pid_file)!r}).write_text(str(grand.pid))
        print("GRANDCHILD_PID_WRITTEN", flush=True)
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            start_new_session=True,
        )
        Path({str(child_pid_file)!r}).write_text(str(child.pid))
        print("CHILD_PID_WRITTEN", flush=True)
        time.sleep(30)
        """
    )
    runner_script = textwrap.dedent(
        f"""
        import sys
        from pathlib import Path
        sys.path.insert(0, {str(ROOT)!r})
        from scripts.execution_control.process_tree import run_owned_command
        print("RUNNER_READY", flush=True)
        try:
            run_owned_command(
                [sys.executable, "-c", {owned_script!r}],
                cwd=Path({str(ROOT)!r}),
                env=None,
                hard_seconds=60.0,
                soft_seconds=30.0,
                stall_seconds=None,
                termination_grace_seconds=0.5,
                tracker=None,
                enforce_hard=True,
                enforce_stall=False,
            )
        except KeyboardInterrupt:
            raise SystemExit(130)
        """
    )
    runner = subprocess.Popen(
        [sys.executable, "-u", "-c", runner_script],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        _wait_for_markers(runner, ("RUNNER_READY",), timeout=10.0)
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if child_pid_file.is_file() and grandchild_pid_file.is_file():
                break
            time.sleep(0.05)
        assert child_pid_file.is_file(), "child PID file missing"
        assert grandchild_pid_file.is_file(), "grandchild PID file missing"
        child_pid = int(child_pid_file.read_text(encoding="utf-8"))
        grandchild_pid = int(grandchild_pid_file.read_text(encoding="utf-8"))
        os.kill(runner.pid, signal.SIGINT)
        runner.wait(timeout=10)
        assert runner.returncode == 130
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if not _pid_alive(child_pid) and not _pid_alive(grandchild_pid):
                break
            time.sleep(0.05)
        assert not _pid_alive(child_pid)
        assert not _pid_alive(grandchild_pid)
        assert _pid_alive(unrelated.pid)
    finally:
        if runner.stdout is not None:
            runner.stdout.close()
        if runner.poll() is None:
            runner.kill()
            runner.wait(timeout=5)
    unrelated.send_signal(signal.SIGTERM)
    unrelated.wait(timeout=5)
