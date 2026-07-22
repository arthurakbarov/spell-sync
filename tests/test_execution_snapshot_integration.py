"""Snapshot gate integration tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.workspace_paths import resolve_spell_sync_dev_root  # noqa: E402


def _snapshot_env(isolated_state_dir) -> dict[str, str]:
    env = dict(os.environ)
    env["XDG_STATE_HOME"] = str(isolated_state_dir)
    dev_root = resolve_spell_sync_dev_root(ROOT)
    if dev_root is not None:
        env["SPELL_SYNC_DEV_ROOT"] = str(dev_root)
    return env


def test_snapshot_gate_emits_execution_gate_marker(isolated_state_dir):
    dev_root = resolve_spell_sync_dev_root(ROOT)
    if dev_root is None:
        return
    proc = subprocess.run(
        [sys.executable, "scripts/run_snapshot_tests.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        env=_snapshot_env(isolated_state_dir),
    )
    output = proc.stdout + proc.stderr
    assert "EXECUTION_GATE=gate:snapshot-tests" in output
    assert proc.returncode == 0
    assert "SNAPSHOT_STEP=pytest" in output


def test_snapshot_child_mappings_exist():
    from scripts.execution_control.registry import REGISTRY_REL_PATH, load_registry

    registry = load_registry(ROOT / REGISTRY_REL_PATH)
    for step in (
        "snapshot-tests:pytest",
        "snapshot-tests:git",
        "snapshot-tests:archive-create",
        "snapshot-tests:archive-check",
    ):
        assert step in registry.child_mappings
