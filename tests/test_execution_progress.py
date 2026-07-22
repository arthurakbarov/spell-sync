"""Progress contract tests."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from scripts.execution_control.process_tree import run_owned_command
from scripts.execution_control.progress import ProgressTracker, create_tracker
from tests.conftest_execution import sleep_command, spam_command

ROOT = Path(__file__).resolve().parents[1]


def test_pytest_progress_renews_lease():
    tracker = create_tracker("pytest-node-transition")
    assert tracker is not None
    tracker.observe_line("tests/test_x.py::test_y PASSED")
    assert tracker.progress_age() < 0.2


def test_repeated_noise_does_not_renew_indefinitely():
    tracker = ProgressTracker(contract_id="artifact-state-transition")
    for _ in range(100):
        tracker.observe_line("same-line")
    before = tracker.event_count
    for _ in range(100):
        tracker.observe_line("same-line")
    assert tracker.event_count == before


def test_quiet_command_not_stall_killed(isolated_state_dir):
    del isolated_state_dir
    tracker = create_tracker("ci-child-transition")
    result = run_owned_command(
        sleep_command(0.2),
        cwd=ROOT,
        env=None,
        hard_seconds=2.0,
        soft_seconds=0.05,
        stall_seconds=0.1,
        termination_grace_seconds=0.05,
        tracker=tracker,
        enforce_hard=True,
        enforce_stall=False,
    )
    assert result.timed_out is False
    assert result.exit_code == 0


def test_hard_deadline_absolute(isolated_state_dir):
    del isolated_state_dir
    with pytest.raises(subprocess.TimeoutExpired):
        subprocess.run(sleep_command(2.0), timeout=0.2, check=False)
    result = run_owned_command(
        sleep_command(1.0),
        cwd=ROOT,
        env=None,
        hard_seconds=0.2,
        soft_seconds=0.1,
        stall_seconds=None,
        termination_grace_seconds=0.05,
        tracker=None,
        enforce_hard=True,
        enforce_stall=False,
    )
    assert result.timed_out is True
    assert result.timeout_kind == "hard"


def test_stdout_spam_does_not_defeat_hard_limit(isolated_state_dir):
    del isolated_state_dir
    tracker = create_tracker("artifact-state-transition")
    result = run_owned_command(
        spam_command(1.0),
        cwd=ROOT,
        env=None,
        hard_seconds=0.25,
        soft_seconds=0.1,
        stall_seconds=0.2,
        termination_grace_seconds=0.05,
        tracker=tracker,
        enforce_hard=True,
        enforce_stall=True,
    )
    assert result.timed_out is True


def test_ci_child_transition_marks_phase_lines():
    tracker = create_tracker("ci-child-transition")
    tracker.observe_line("ruff.check: passed")
    assert tracker.event_count >= 1


def test_maximum_gap_tracks_idle_period():
    tracker = ProgressTracker(contract_id="pytest-node-transition")
    tracker.observe_line("tests/a.py::test_one PASSED")
    time.sleep(0.08)
    tracker.observe_line("tests/a.py::test_two PASSED")
    assert tracker.maximum_gap >= 0.05
