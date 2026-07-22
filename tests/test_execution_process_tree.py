"""Process tree termination tests."""

from __future__ import annotations

import signal
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.execution_control.process_tree import run_owned_command
from scripts.execution_control.progress import create_tracker
from tests.conftest_execution import (
    echo_command,
    exit_command,
    grandchild_command,
    marker_sleep_command,
    sleep_command,
)

ROOT = Path(__file__).resolve().parents[1]


def test_fast_command_preserves_exit_code(isolated_state_dir):
    del isolated_state_dir
    result = run_owned_command(
        exit_command(42),
        cwd=ROOT,
        env=None,
        hard_seconds=2.0,
        soft_seconds=1.0,
        stall_seconds=None,
        termination_grace_seconds=0.3,
        tracker=None,
    )
    assert result.timed_out is False
    assert result.exit_code == 42


def test_hard_timeout_terminates_sleeping_process(isolated_state_dir):
    del isolated_state_dir
    with pytest.raises(subprocess.TimeoutExpired):
        subprocess.run(sleep_command(2.0), timeout=0.2, check=False)
    result = run_owned_command(
        sleep_command(10.0),
        cwd=ROOT,
        env=None,
        hard_seconds=0.3,
        soft_seconds=0.2,
        stall_seconds=None,
        termination_grace_seconds=0.3,
        tracker=None,
        enforce_hard=True,
    )
    assert result.timed_out is True
    assert result.timeout_kind == "hard"
    assert result.exit_code == 124
    assert result.duration_seconds < 2.0


def test_grandchild_terminated_on_hard_timeout(isolated_state_dir):
    del isolated_state_dir
    result = run_owned_command(
        grandchild_command(2.0),
        cwd=ROOT,
        env=None,
        hard_seconds=0.3,
        soft_seconds=0.1,
        stall_seconds=None,
        termination_grace_seconds=0.1,
        tracker=None,
        enforce_hard=True,
        enforce_stall=False,
    )
    assert result.timed_out is True
    assert result.exit_code == 124


def test_stall_timeout_when_enforced(isolated_state_dir):
    del isolated_state_dir
    tracker = create_tracker("artifact-state-transition")
    result = run_owned_command(
        sleep_command(1.0),
        cwd=ROOT,
        env=None,
        hard_seconds=2.0,
        soft_seconds=0.05,
        stall_seconds=0.1,
        termination_grace_seconds=0.05,
        tracker=tracker,
        enforce_hard=True,
        enforce_stall=True,
    )
    assert result.timed_out is True
    assert result.timeout_kind == "stall"


def test_unrelated_process_untouched_on_hard_timeout(isolated_state_dir):
    del isolated_state_dir
    marker = "EXEC_UNRELATED_MARKER_9c2b"
    outsider = subprocess.Popen(
        marker_sleep_command(marker, 3.0),
        start_new_session=True,
    )
    try:
        result = run_owned_command(
            sleep_command(5.0),
            cwd=ROOT,
            env=None,
            hard_seconds=0.35,
            soft_seconds=0.2,
            stall_seconds=None,
            termination_grace_seconds=0.3,
            tracker=None,
        )
        assert result.timed_out is True
        assert outsider.poll() is None
    finally:
        outsider.send_signal(signal.SIGTERM)
        outsider.wait(timeout=2)


def test_progress_output_captured_in_tail(isolated_state_dir):
    del isolated_state_dir
    result = run_owned_command(
        echo_command("tests/demo.py::test_demo PASSED"),
        cwd=ROOT,
        env=None,
        hard_seconds=2.0,
        soft_seconds=1.0,
        stall_seconds=None,
        termination_grace_seconds=0.3,
        tracker=create_tracker("pytest-node-transition"),
    )
    assert "tests/demo.py::test_demo PASSED" in result.stdout_tail
    assert result.progress_event_count >= 1


def test_child_exit_code_preserved(isolated_state_dir):
    del isolated_state_dir
    command = [sys.executable, "-c", "raise SystemExit(7)"]
    result = run_owned_command(
        command,
        cwd=ROOT,
        env=None,
        hard_seconds=2.0,
        soft_seconds=1.0,
        stall_seconds=None,
        termination_grace_seconds=0.1,
        tracker=None,
        enforce_hard=True,
        enforce_stall=False,
    )
    assert result.exit_code == 7
    assert result.timed_out is False
