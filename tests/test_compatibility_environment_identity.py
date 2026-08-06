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


def test_experimental_without_source_only_is_rejected() -> None:
    actual_platform = {"darwin": "macos", "linux": "linux", "windows": "windows"}[
        platform.system().lower()
    ]
    major_minor = ".".join(platform.python_version().split(".")[:2])
    code, payload = _run_compatibility(
        "--platform",
        actual_platform,
        "--python-version",
        major_minor,
        "--experimental",
    )
    assert code == 1
    assert payload.get("failedId") == "compatibility.experimental-requires-source-only"
    assert payload.get("sourceOnly") is False
    assert payload.get("experimental") is True


def test_source_only_payload_skips_wheel_steps(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Source-only mode must not invoke the wheel compatibility path."""
    import scripts.run_compatibility_checks as compat

    actual_platform = {"darwin": "macos", "linux": "linux", "windows": "windows"}[
        platform.system().lower()
    ]
    major_minor = ".".join(platform.python_version().split(".")[:2])

    def fake_run(command, **_kwargs):  # type: ignore[no-untyped-def]
        return 0, "ok"

    def boom_wheels(_host_python: str):  # type: ignore[no-untyped-def]
        raise AssertionError("wheel path must not run in source-only mode")

    monkeypatch.setattr(compat, "_run", fake_run)
    monkeypatch.setattr(compat, "_run_wheel_compatibility", boom_wheels)
    code = compat.main(
        [
            "--platform",
            actual_platform,
            "--python-version",
            major_minor,
            "--experimental",
            "--source-only",
            "--format",
            "json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload.get("sourceOnly") is True
    assert payload.get("experimental") is True
    assert "source-only" in str(payload.get("executionId"))
    steps = payload.get("steps") or []
    assert any(
        isinstance(step, dict) and step.get("step") == "compatibility.wheel-skipped-source-only"
        for step in steps
    )
    assert not any(
        isinstance(step, dict) and str(step.get("step", "")).startswith("compatibility.wheel-build")
        for step in steps
    )
