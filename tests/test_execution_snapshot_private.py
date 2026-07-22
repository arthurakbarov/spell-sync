"""Private snapshot gate integration tests (hermetic only)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

from tests.test_execution_snapshot_output_isolation import (  # noqa: E402
    _build_hermetic_workspace,
)


def test_snapshot_private_gate_uses_hermetic_fixture(isolated_state_dir, tmp_path):
    del isolated_state_dir
    workspace, output = _build_hermetic_workspace(tmp_path)
    env = dict(os.environ)
    env["XDG_STATE_HOME"] = str(tmp_path / "state")
    env["SPELL_SYNC_DEV_ROOT"] = str(workspace / "spell-sync-dev")
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/run_snapshot_tests.py",
            "--workspace-root",
            str(workspace),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    combined = proc.stdout + proc.stderr
    assert "EXECUTION_GATE=gate:snapshot-tests" in combined
    assert "SNAPSHOT_STEP=pytest" in combined
    assert "tarfile.open" not in combined
    assert proc.returncode == 0
