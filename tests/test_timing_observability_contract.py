"""Timing observability validator is wired into CI and polish paths."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_timing_observability_validator_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/validate_timing_observability.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "TIMING_OBSERVABILITY_VALIDATION=success" in proc.stdout
