#!/usr/bin/env python3
"""Semantic invariants for doctor JSON payloads (stdlib; no jsonschema runtime dep)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "docs" / "technical" / "doctor-report.schema.json"

REQUIRED_KEYS = (
    "command",
    "exit",
    "ok",
    "wordlist_path",
    "wordlist_count",
    "version",
    "dictionaries_total",
    "dictionaries_readable",
    "dictionaries_writable",
    "actions",
    "checks",
    "required_action_count",
)


def validate_doctor_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in REQUIRED_KEYS:
        if key not in payload:
            errors.append(f"missing:{key}")
    if payload.get("command") not in (None, "doctor"):
        errors.append("command:must-be-doctor")
    exit_code = payload.get("exit")
    if not isinstance(exit_code, int) or exit_code < 0:
        errors.append("exit:non-negative-int")
    if not isinstance(payload.get("ok"), bool):
        errors.append("ok:bool")
    actions = payload.get("actions")
    if not isinstance(actions, list):
        errors.append("actions:list")
    else:
        required_count = sum(
            1 for item in actions if isinstance(item, dict) and item.get("optional") is False
        )
        declared = payload.get("required_action_count")
        if isinstance(declared, int) and declared != required_count:
            errors.append("required_action_count:mismatch")
        for index, item in enumerate(actions):
            if not isinstance(item, dict):
                errors.append(f"actions[{index}]:object")
                continue
            for field in ("id", "reason", "optional"):
                if field not in item:
                    errors.append(f"actions[{index}]:missing:{field}")
    checks = payload.get("checks")
    if not isinstance(checks, list):
        errors.append("checks:list")
    else:
        for index, item in enumerate(checks):
            if not isinstance(item, dict):
                errors.append(f"checks[{index}]:object")
                continue
            if "level" not in item or "message" not in item:
                errors.append(f"checks[{index}]:missing-level-or-message")
            level = item.get("level")
            if level not in (None, "info", "warn", "error", "detail"):
                errors.append(f"checks[{index}]:bad-level")
    # Privacy: no obvious absolute home paths in string fields
    blob = json.dumps(payload, ensure_ascii=True)
    if "/Users/" in blob or "/home/" in blob:
        errors.append("privacy:absolute-home-path")
    return errors


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not SCHEMA_PATH.is_file():
        print("DOCTOR_SCHEMA_RESULT=failed")
        print("DOCTOR_SCHEMA_REASON=schema-missing")
        return 1
    # Schema file must stay valid JSON even without a runtime validator dependency.
    json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if not args:
        print("DOCTOR_SCHEMA_RESULT=success")
        print(f"DOCTOR_SCHEMA_PATH={SCHEMA_PATH}")
        print("DOCTOR_SCHEMA_MODE=schema-only")
        return 0
    path = Path(args[0])
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        print("DOCTOR_SCHEMA_RESULT=failed")
        print("DOCTOR_SCHEMA_REASON=payload-not-object")
        return 1
    errors = validate_doctor_payload(payload)
    if errors:
        print("DOCTOR_SCHEMA_RESULT=failed")
        for err in errors:
            print(f"DOCTOR_SCHEMA_ERROR={err}")
        return 1
    print("DOCTOR_SCHEMA_RESULT=success")
    print(f"DOCTOR_SCHEMA_PATH={SCHEMA_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
