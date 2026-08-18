"""Pytest strictness and warning policy markers."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_pytest_strict_options_configured() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "--strict-config" in pyproject
    assert "--strict-markers" in pyproject
