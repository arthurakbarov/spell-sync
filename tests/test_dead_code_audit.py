"""Dead-code audit produces a sanitized report and fails closed on findings."""

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
    assert "DEAD_CODE_AUDIT_RESULT=success" in proc.stdout
    assert "DEAD_CODE_SCANNED_SMALL=" in proc.stdout
    scanned = int(proc.stdout.split("DEAD_CODE_SCANNED_SMALL=")[1].splitlines()[0])
    assert scanned > 0, "dead-code scan must not be vacuous (zero small product files)"
    report = ROOT / ".artifacts/quality/dead-code-report.json"
    assert report.is_file()
    raw = report.read_text(encoding="utf-8")
    assert "/Users/" not in raw
    payload = json.loads(raw)
    assert payload["scannedSmallFileCount"] == scanned
    assert payload["maxCandidateBytes"] >= 238


def test_dead_code_audit_fails_closed_on_tiny_unreferenced_module() -> None:
    probe = ROOT / "spell_sync" / "_dead_code_audit_probe_tmp.py"
    probe.write_text("probe = 1\n", encoding="utf-8")
    try:
        proc = subprocess.run(
            [sys.executable, "scripts/audit_dead_code.py"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "DEAD_CODE_AUDIT_RESULT=review-required" in proc.stdout
        report = json.loads(
            (ROOT / ".artifacts/quality/dead-code-report.json").read_text(encoding="utf-8")
        )
        paths = {item["path"] for item in report["candidates"]}
        assert "spell_sync/_dead_code_audit_probe_tmp.py" in paths
    finally:
        probe.unlink(missing_ok=True)
        subprocess.run(
            [sys.executable, "scripts/audit_dead_code.py"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
