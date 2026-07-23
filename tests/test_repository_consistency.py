"""Repository consistency validator succeeds on clean tree."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_repository_consistency_validator() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/validate_repository_consistency.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "REPOSITORY_CONSISTENCY_RESULT=success" in proc.stdout
