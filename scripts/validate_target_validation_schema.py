#!/usr/bin/env python3
"""Shape invariants for docs/technical/target-validation.json (stdlib; no jsonschema runtime dep)."""

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "docs" / "technical" / "target-validation.schema.json"
DEFAULT_PAYLOAD = ROOT / "docs" / "technical" / "target-validation.json"
EXAMPLE_PATH = ROOT / "docs" / "examples" / "target-validation-entry.example.json"

REQUIRED_ROOT = ("schema_version", "targets")
REQUIRED_ENTRY = (
    "target_id",
    "platform",
    "implementation",
    "automated_validation",
    "manual_validation",
    "application_version",
    "tested_on",
    "notes",
    "evidence",
)
ALLOWED_ENTRY = frozenset(REQUIRED_ENTRY)
PLATFORMS = frozenset({"linux", "macos", "windows"})
IMPLEMENTATION = frozenset({"implemented", "experimental", "not-implemented"})
AUTOMATED = frozenset({"pass", "fail", "partial", "not-run"})
MANUAL = frozenset({"pass", "fail", "not-run", "experimental"})


def validate_target_validation_payload(payload: dict[str, Any]) -> list[str]:
    """Return human-readable shape errors (semantic registry checks live elsewhere)."""
    errors: list[str] = []
    for key in REQUIRED_ROOT:
        if key not in payload:
            errors.append(f"missing:{key}")
    if payload.get("schema_version") != 1:
        errors.append("schema_version:must-be-1")
    unknown_root = sorted(set(payload) - set(REQUIRED_ROOT))
    for key in unknown_root:
        errors.append(f"unknown-root:{key}")
    targets = payload.get("targets")
    if not isinstance(targets, list):
        errors.append("targets:list")
        return errors
    if not targets:
        errors.append("targets:empty")
    for index, item in enumerate(targets):
        prefix = f"targets[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix}:object")
            continue
        for key in REQUIRED_ENTRY:
            if key not in item:
                errors.append(f"{prefix}:missing:{key}")
        for key in sorted(set(item) - ALLOWED_ENTRY):
            errors.append(f"{prefix}:unknown:{key}")
        target_id = item.get("target_id")
        if not isinstance(target_id, str) or not target_id.strip():
            errors.append(f"{prefix}:target_id:non-empty-string")
        platform = item.get("platform")
        if platform not in PLATFORMS:
            errors.append(f"{prefix}:platform:enum")
        if item.get("implementation") not in IMPLEMENTATION:
            errors.append(f"{prefix}:implementation:enum")
        if item.get("automated_validation") not in AUTOMATED:
            errors.append(f"{prefix}:automated_validation:enum")
        if item.get("manual_validation") not in MANUAL:
            errors.append(f"{prefix}:manual_validation:enum")
        for field in ("application_version", "notes", "evidence"):
            value = item.get(field)
            if value is not None and not isinstance(value, str):
                errors.append(f"{prefix}:{field}:string-or-null")
        tested_on = item.get("tested_on")
        if tested_on is not None:
            if not isinstance(tested_on, str):
                errors.append(f"{prefix}:tested_on:string-or-null")
            else:
                try:
                    date.fromisoformat(tested_on)
                except ValueError:
                    errors.append(f"{prefix}:tested_on:iso-date")
        if item.get("manual_validation") == "pass":
            if not item.get("application_version"):
                errors.append(f"{prefix}:manual-pass:requires-application_version")
            if not tested_on:
                errors.append(f"{prefix}:manual-pass:requires-tested_on")
    return errors


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not SCHEMA_PATH.is_file():
        print("TARGET_VALIDATION_SCHEMA_RESULT=failed")
        print("TARGET_VALIDATION_SCHEMA_REASON=schema-missing")
        return 1
    json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if not args:
        payload_path = DEFAULT_PAYLOAD
    else:
        payload_path = Path(args[0])
    if not payload_path.is_file():
        print("TARGET_VALIDATION_SCHEMA_RESULT=failed")
        print("TARGET_VALIDATION_SCHEMA_REASON=payload-missing")
        return 1
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        print("TARGET_VALIDATION_SCHEMA_RESULT=failed")
        print("TARGET_VALIDATION_SCHEMA_REASON=payload-not-object")
        return 1
    errors = validate_target_validation_payload(payload)
    if errors:
        print("TARGET_VALIDATION_SCHEMA_RESULT=failed")
        for err in errors:
            print(f"TARGET_VALIDATION_SCHEMA_ERROR={err}")
        return 1
    print("TARGET_VALIDATION_SCHEMA_RESULT=success")
    print("TARGET_VALIDATION_SCHEMA_PATH=docs/technical/target-validation.schema.json")
    try:
        rel = payload_path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        rel = payload_path.name
    print(f"TARGET_VALIDATION_PAYLOAD={rel}")
    if EXAMPLE_PATH.is_file():
        example = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
        if not isinstance(example, dict):
            print("TARGET_VALIDATION_SCHEMA_RESULT=failed")
            print("TARGET_VALIDATION_SCHEMA_REASON=example-not-object")
            return 1
        # Accept either a full document or a bare entry object.
        if "targets" in example:
            example_payload = example
        else:
            example_payload = {"schema_version": 1, "targets": [example]}
        example_errors = validate_target_validation_payload(example_payload)
        if example_errors:
            print("TARGET_VALIDATION_SCHEMA_RESULT=failed")
            print("TARGET_VALIDATION_SCHEMA_REASON=example-invalid")
            for err in example_errors:
                print(f"TARGET_VALIDATION_SCHEMA_ERROR=example:{err}")
            return 1
        print("TARGET_VALIDATION_EXAMPLE=docs/examples/target-validation-entry.example.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
