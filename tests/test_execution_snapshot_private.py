"""Private snapshot gate integration tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.workspace_paths import resolve_spell_sync_dev_root  # noqa: E402


def test_snapshot_private_root_resolves():
    dev_root = resolve_spell_sync_dev_root(ROOT)
    assert dev_root is not None
    assert (dev_root / "scripts" / "create-code-snapshot.py").is_file()
    assert (dev_root / "tests" / "test_create_code_snapshot.py").is_file()


def test_snapshot_gate_blocked_without_private_root(isolated_state_dir):
    del isolated_state_dir
    proc = subprocess.run(
        [sys.executable, "scripts/run_snapshot_tests.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "SPELL_SYNC_DEV_ROOT": "/nonexistent/spell-sync-dev-root"},
    )
    output = proc.stdout + proc.stderr
    assert "SNAPSHOT_GATE_RESULT=blocked" in output
    assert "snapshot.private-root-unavailable" in output
    assert proc.returncode != 0


def test_snapshot_gate_runs_private_pytest_when_available():
    dev_root = resolve_spell_sync_dev_root(ROOT)
    if dev_root is None:
        return
    proc = subprocess.run(
        [sys.executable, "scripts/run_snapshot_tests.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "SPELL_SYNC_DEV_ROOT": str(dev_root)},
    )
    output = proc.stdout + proc.stderr
    assert "EXECUTION_GATE=gate:snapshot-tests" in output
    assert "SNAPSHOT_STEP=pytest" in output
    assert "tarfile.open" not in output
