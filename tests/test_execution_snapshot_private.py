"""Private snapshot gate integration tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.workspace_paths import (  # noqa: E402
    resolve_snapshot_workspace_layout,
    resolve_spell_sync_dev_root,
)


def test_snapshot_private_root_resolves():
    dev_root = resolve_spell_sync_dev_root(ROOT)
    assert dev_root is not None
    assert (dev_root / "scripts" / "create-code-snapshot.py").is_file()
    assert (dev_root / "tests" / "test_create_code_snapshot.py").is_file()


def test_snapshot_gate_blocked_without_workspace_root(isolated_state_dir, tmp_path):
    del isolated_state_dir
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/run_snapshot_tests.py",
            "--workspace-root",
            str(tmp_path / "missing-layout"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "SPELL_SYNC_DEV_ROOT": "/nonexistent/spell-sync-dev-root"},
    )
    output = proc.stdout + proc.stderr
    assert "SNAPSHOT_GATE_RESULT=blocked" in output
    assert "snapshot.workspace-layout-invalid" in output
    assert proc.returncode != 0


def test_snapshot_gate_runs_private_pytest_when_workspace_available():
    dev_root = resolve_spell_sync_dev_root(ROOT)
    if dev_root is None:
        return
    layout = resolve_snapshot_workspace_layout(dev_root.parent)
    if layout is None:
        return
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/run_snapshot_tests.py",
            "--workspace-root",
            str(layout.root),
        ],
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
