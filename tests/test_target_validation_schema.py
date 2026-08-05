"""Tests for target-validation JSON schema shape checks."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.validate_target_validation_schema import (  # noqa: E402
    SCHEMA_PATH,
    validate_target_validation_payload,
)


def _load_matrix() -> dict:
    return json.loads((ROOT / "docs" / "target-validation.json").read_text(encoding="utf-8"))


def test_schema_file_is_valid_json() -> None:
    assert SCHEMA_PATH.is_file()
    payload = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert payload["title"]


def test_repository_matrix_passes_shape() -> None:
    errors = validate_target_validation_payload(_load_matrix())
    assert errors == []


def test_example_entry_passes_shape() -> None:
    path = ROOT / "docs" / "examples" / "target-validation-entry.example.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert validate_target_validation_payload(payload) == []


def test_missing_required_field_fails() -> None:
    payload = _load_matrix()
    entry = copy.deepcopy(payload["targets"][0])
    del entry["evidence"]
    errors = validate_target_validation_payload({"schema_version": 1, "targets": [entry]})
    assert any("missing:evidence" in err for err in errors)


def test_bad_manual_enum_fails() -> None:
    payload = _load_matrix()
    entry = copy.deepcopy(payload["targets"][0])
    entry["manual_validation"] = "maybe"
    errors = validate_target_validation_payload({"schema_version": 1, "targets": [entry]})
    assert any("manual_validation:enum" in err for err in errors)


def test_manual_pass_requires_version_and_date() -> None:
    entry = {
        "target_id": "chrome",
        "platform": "macos",
        "implementation": "implemented",
        "automated_validation": "pass",
        "manual_validation": "pass",
        "application_version": None,
        "tested_on": None,
        "notes": None,
        "evidence": None,
    }
    errors = validate_target_validation_payload({"schema_version": 1, "targets": [entry]})
    assert any("requires-application_version" in err for err in errors)
    assert any("requires-tested_on" in err for err in errors)


def test_validate_script_on_repository_matrix() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_target_validation_schema.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "TARGET_VALIDATION_SCHEMA_RESULT=success" in proc.stdout


def test_check_target_capabilities_uses_shape_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import check_target_capabilities

    calls: list[dict] = []

    def fake_validate(payload: dict) -> list[str]:
        calls.append(payload)
        return ["shape:boom"]

    monkeypatch.setattr(
        check_target_capabilities,
        "validate_target_validation_payload",
        fake_validate,
    )
    errors = check_target_capabilities._validate(_load_matrix())
    assert calls
    assert "shape:boom" in errors
