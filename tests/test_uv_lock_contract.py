"""uv.lock presence and lockfile consistency checks."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UV_LOCK_PATH = ROOT / "uv.lock"


def test_uv_lock_exists_and_is_non_empty() -> None:
    assert UV_LOCK_PATH.is_file(), "[ENVIRONMENT-LOCK-004] missing uv.lock"
    assert UV_LOCK_PATH.read_text(encoding="utf-8").strip()


def test_uv_lock_check_passes() -> None:
    proc = subprocess.run(
        ["uv", "lock", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = proc.stdout + proc.stderr
    assert proc.returncode == 0, output


def test_uv_lock_references_project_metadata() -> None:
    lock_text = UV_LOCK_PATH.read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = __import__("re").search(r'^name = "([^"]+)"', pyproject, re.MULTILINE)
    assert match is not None
    project_name = match.group(1)
    assert project_name in lock_text
