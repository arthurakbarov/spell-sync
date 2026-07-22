"""Compatibility checks reject platform/Python identity mismatches."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _run_compatibility(*args: str) -> tuple[int, dict[str, object]]:
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_compatibility_checks.py"),
            *args,
            "--format",
            "json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    payload = json.loads(proc.stdout)
    return proc.returncode, payload


def test_rejects_wrong_platform_argument() -> None:
    actual = platform.system().lower()
    wrong = "windows" if actual in {"darwin", "linux"} else "linux"
    code, payload = _run_compatibility(
        "--platform", wrong, "--python-version", platform.python_version()
    )
    assert code == 1
    assert payload.get("failedId") == "compatibility.environment-mismatch"


def test_rejects_wrong_python_version_argument() -> None:
    actual_platform = {"darwin": "macos", "linux": "linux", "windows": "windows"}[
        platform.system().lower()
    ]
    wrong_python = "9.99.99"
    if platform.python_version().startswith(wrong_python):
        pytest.skip("cannot pick a non-matching python version on this runtime")
    code, payload = _run_compatibility(
        "--platform", actual_platform, "--python-version", wrong_python
    )
    assert code == 1
    assert payload.get("failedId") == "compatibility.environment-mismatch"
