"""Dependency groups follow maintainer SSOT."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dependency_group_validator_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/validate_dependency_groups.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "DEPENDENCY_GROUP_VALIDATION=success" in proc.stdout


def test_runtime_includes_textual() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "textual" in text
    assert 'name = "textual"' in (ROOT / "uv.lock").read_text(encoding="utf-8")
