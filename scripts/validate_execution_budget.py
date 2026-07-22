#!/usr/bin/env python3
"""Validate execution budget registry and integration contracts."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execution_control.paths import history_database_path, state_root  # noqa: E402
from scripts.execution_control.registry import (  # noqa: E402
    REGISTRY_REL_PATH,
    load_registry,
    validate_registry,
)

MONITORED_FILES = (
    "scripts/ci_runner.py",
    "scripts/run_focused_tests.py",
    "scripts/run_pre_final_checks.py",
    "scripts/test_plan.py",
)

FORBIDDEN_PATTERNS = (
    (re.compile(r"\|\s*tail\b"), "[EXECUTION-CONTROL-BOUNDARY-003] tail pipeline forbidden"),
    (re.compile(r"\|\s*tee\b"), "[EXECUTION-CONTROL-BOUNDARY-003] tee pipeline forbidden"),
)


def main() -> int:
    errors: list[str] = []
    try:
        registry = load_registry(ROOT / REGISTRY_REL_PATH)
    except ValueError as exc:
        print(f"[EXECUTION-CONTROL-SCHEMA-001] {exc}")
        return 1
    errors.extend(validate_registry(registry))

    state = state_root()
    if str(state).startswith(str(ROOT.resolve())):
        errors.append("[EXECUTION-CONTROL-PRIVACY-005] state directory must be outside repository")

    db = history_database_path()
    if str(db).startswith(str(ROOT.resolve())):
        errors.append("[EXECUTION-CONTROL-PRIVACY-005] history database must be outside repository")

    gitignore = ROOT / ".gitignore"
    if not gitignore.is_file():
        errors.append("[EXECUTION-CONTROL-PRIVACY-005] .gitignore must exist")
    elif ".artifacts/" not in gitignore.read_text(encoding="utf-8"):
        errors.append("[EXECUTION-CONTROL-PRIVACY-005] .artifacts/ must remain gitignore")

    for rel in MONITORED_FILES:
        path = ROOT / rel
        if not path.is_file():
            errors.append(f"[EXECUTION-CONTROL-BOUNDARY-003] missing monitored file {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        if not any(
            marker in text
            for marker in ("run_monitored_command", "ExecutionController", "assess_admission")
        ):
            errors.append(f"[EXECUTION-CONTROL-BOUNDARY-003] {rel} must use execution controller")
        for pattern, message in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                errors.append(message)

    product_paths = (
        "spell_sync/application/services/pull.py",
        "spell_sync/application/services/push.py",
        "spell_sync/application/services/recovery.py",
    )
    for rel in product_paths:
        path = ROOT / rel
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            if "execution_control" in text or "run_monitored_command" in text:
                errors.append(
                    f"[EXECUTION-CONTROL-BOUNDARY-003] product path must not use controller: {rel}"
                )

    if errors:
        for item in errors:
            print(item)
        print(f"EXECUTION_BUDGET_VALIDATION=failed checks={len(errors)}")
        return 1
    print("EXECUTION_BUDGET_VALIDATION=success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
