"""dev-commands registry and generated DEVELOPMENT table."""

from __future__ import annotations

from pathlib import Path

from scripts.validate_dev_commands import MARKER_END, MARKER_START, main, validate

ROOT = Path(__file__).resolve().parents[1]


def test_dev_commands_validate_clean():
    assert validate() == []


def test_dev_commands_cli_check():
    assert main(["--check"]) == 0


def test_development_markers_present():
    text = (ROOT / "docs" / "DEVELOPMENT.md").read_text(encoding="utf-8")
    assert MARKER_START in text
    assert MARKER_END in text
