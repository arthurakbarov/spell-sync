"""Dead-code audit produces a sanitized report."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dead_code_audit_runs() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/audit_dead_code.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "DEAD_CODE_AUDIT_RESULT=" in proc.stdout
    report = ROOT / ".artifacts/quality/dead-code-report.json"
    assert report.is_file()
    raw = report.read_text(encoding="utf-8")
    assert "/Users/" not in raw
    json.loads(raw)
