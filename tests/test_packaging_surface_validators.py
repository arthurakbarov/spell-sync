"""Packaging-surface validators run via focused plans and CI pytest."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_support_matrix_validator_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/validate_support_matrix.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SUPPORT_MATRIX_VALIDATION=success" in proc.stdout


def test_package_members_validator_skips_without_dist() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/validate_package_members.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PACKAGE_MEMBERS_RESULT=" in proc.stdout


def test_snapshot_policy_validator_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/validate_snapshot_policy.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SNAPSHOT_POLICY_VALIDATION=success" in proc.stdout
