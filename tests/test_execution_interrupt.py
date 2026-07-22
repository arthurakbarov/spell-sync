"""Keyboard interrupt cleanup tests."""

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


def test_sigint_terminates_owned_tree_and_preserves_unrelated(isolated_state_dir):
    del isolated_state_dir
    unrelated = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        start_new_session=True,
    )
    script = textwrap.dedent(
        f"""
        import os, sys, time
        sys.path.insert(0, {str(ROOT)!r})
        from scripts.execution_control.process_tree import run_owned_command
        from pathlib import Path
        command = [
            sys.executable, "-c",
            "import subprocess, sys, time; "
            "grand=[sys.executable, '-c', 'import time; time.sleep(30)']; "
            "child=[sys.executable, '-c', "
            "'import subprocess, sys, time; "
            "subprocess.Popen(grand, start_new_session=True); time.sleep(30)']; "
            "subprocess.Popen(child, start_new_session=True); time.sleep(30)",
        ]
        try:
            run_owned_command(
                command,
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
        [sys.executable, "-c", script],
        start_new_session=True,
    )
    time.sleep(0.4)
    os.kill(runner.pid, signal.SIGINT)
    runner.wait(timeout=10)
    assert runner.returncode == 130
    assert _pid_alive(unrelated.pid)
    unrelated.send_signal(signal.SIGTERM)
    unrelated.wait(timeout=5)
