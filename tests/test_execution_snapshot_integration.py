"""Snapshot gate integration tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_snapshot_gate_emits_execution_gate_marker():
    proc = subprocess.run(
        [sys.executable, "scripts/run_snapshot_tests.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
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
