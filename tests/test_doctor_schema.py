"""Doctor JSON semantic invariants."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.validate_doctor_schema import validate_doctor_payload

ROOT = Path(__file__).resolve().parents[1]


def _minimal_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "command": "doctor",
        "exit": 0,
        "ok": True,
        "wordlist_path": "wordlist.txt",
        "wordlist_count": 0,
        "version": "0.3.0",
        "dictionaries_total": 0,
        "dictionaries_readable": 0,
        "dictionaries_writable": 0,
        "required_action_count": 0,
        "actions": [],
        "checks": [],
    }
    payload.update(overrides)
    return payload


def test_validate_doctor_payload_ok() -> None:
    assert validate_doctor_payload(_minimal_payload()) == []


def test_validate_doctor_payload_required_action_mismatch() -> None:
    errors = validate_doctor_payload(
        _minimal_payload(
            required_action_count=0,
            actions=[{"id": "fix", "reason": "x", "optional": False}],
        )
    )
    assert "required_action_count:mismatch" in errors


def test_validate_doctor_schema_script() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_doctor_schema.py")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "DOCTOR_SCHEMA_RESULT=success" in proc.stdout
    schema = ROOT / "docs" / "technical" / "doctor-report.schema.json"
    assert schema.is_file()
    json.loads(schema.read_text(encoding="utf-8"))
