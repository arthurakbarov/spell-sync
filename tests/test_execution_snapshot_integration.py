"""Snapshot gate integration tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.registry import REGISTRY_REL_PATH, load_registry  # noqa: E402


def test_snapshot_child_mappings_exist():
    registry = load_registry(ROOT / REGISTRY_REL_PATH)
    for step in (
        "snapshot-tests:pytest",
        "snapshot-tests:git",
        "snapshot-tests:archive-create",
        "snapshot-tests:archive-check",
    ):
        assert step in registry.child_mappings


def test_snapshot_runner_accepts_workspace_root_flag():
    proc = subprocess.run(
        [sys.executable, "scripts/run_snapshot_tests.py", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0
    assert "--workspace-root" in proc.stdout


def test_snapshot_gate_blocked_without_workspace_root_in_pytest(isolated_state_dir, tmp_path):
    del isolated_state_dir
    env = dict(os.environ)
    env["XDG_STATE_HOME"] = str(tmp_path / "state")
    env.pop("SPELL_SYNC_DEV_ROOT", None)
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/run_snapshot_tests.py",
            "--workspace-root",
            str(tmp_path / "invalid-layout"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    output = proc.stdout + proc.stderr
    assert "SNAPSHOT_GATE_FAILED_ID=snapshot.workspace-layout-invalid" in output
