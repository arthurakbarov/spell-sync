"""Dependency report command exposes group exports."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dependency_report_command() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/project_environment.py", "dependency-report"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "DEPENDENCY_REPORT_RESULT=success" in proc.stdout
    assert "group:dev=" in proc.stdout
