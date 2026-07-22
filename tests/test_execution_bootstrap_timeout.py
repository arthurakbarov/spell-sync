"""Pre-gate bootstrap.python must remain bounded."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

from scripts.ci_runner import BOOTSTRAP_PYTHON_HARD_SECONDS, CiRunner  # noqa: E402


def test_bootstrap_python_hang_times_out(isolated_state_dir, tmp_path):
    del isolated_state_dir
    artifacts = tmp_path / "ci"
    runner = CiRunner(root=ROOT, artifacts=artifacts, python_bin=sys.executable)

    real_run = subprocess.run

    def _hang(argv, **kwargs):
        if argv[1:2] == ["-c"] and "sys.version_info" in argv[2]:
            raise subprocess.TimeoutExpired(cmd=argv, timeout=BOOTSTRAP_PYTHON_HARD_SECONDS)
        return real_run(argv, **kwargs)

    with patch("scripts.ci_runner.subprocess.run", side_effect=_hang):
        rc, out, timing = runner._run_bootstrap_python(sys.executable)
    assert rc == 124
    assert timing is not None
    assert timing["result"] == "timeout-hard"
    assert float(timing["hardSeconds"]) == BOOTSTRAP_PYTHON_HARD_SECONDS
    assert "timed out" in out


def test_bootstrap_timeout_prevents_full_gate_children(isolated_state_dir, tmp_path, monkeypatch):
    del isolated_state_dir
    artifacts = tmp_path / "ci"
    runner = CiRunner(root=ROOT, artifacts=artifacts, python_bin=sys.executable)
    gate_calls: list[str] = []

    def _fake_begin(_py: str):
        gate_calls.append("begin")
        return 0, None

    monkeypatch.setattr(runner, "_begin_full_ci_gate", _fake_begin)

    real_run = subprocess.run

    def _hang(argv, **kwargs):
        if argv[1:2] == ["-c"] and "sys.version_info" in argv[2]:
            raise subprocess.TimeoutExpired(cmd=argv, timeout=BOOTSTRAP_PYTHON_HARD_SECONDS)
        return real_run(argv, **kwargs)

    with patch("scripts.ci_runner.subprocess.run", side_effect=_hang):
        rc = runner.run(bootstrap=False, only="execution-budget.registry")
    assert rc == 1
    assert gate_calls == []
