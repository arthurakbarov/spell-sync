"""Public documentation contract checks."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_user_documentation_validator() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/validate_user_documentation.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_readme_not_architecture_first() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    first_block = readme.split("## What the personal word list")[0]
    assert "immutable plan" not in first_block.lower()
    assert "transaction journal" not in first_block.lower()
    assert "Get started" in first_block or "GETTING_STARTED" in first_block


def test_user_documentation_validator_requires_support_report_and_recovery_links() -> None:
    source = (ROOT / "scripts" / "validate_user_documentation.py").read_text(encoding="utf-8")
    assert "readme-cli-support-report" in source
    assert "getting-started-recovery-link" in source
    assert "getting-started-troubleshooting-link" in source
