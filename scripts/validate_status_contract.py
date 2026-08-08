#!/usr/bin/env python3
"""Validate status-contract.json against ExitCode and docs markers."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "scripts" / "contracts" / "status-contract.json"


def validate(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    path = root / "scripts" / "contracts" / "status-contract.json"
    if not path.is_file():
        return ["missing scripts/contracts/status-contract.json"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"status-contract:parse:{exc}"]
    if payload.get("contractId") != "status-contract-v1":
        errors.append("status-contract:contractId")
    if payload.get("schemaVersion") != 1:
        errors.append("status-contract:schemaVersion")
    exit_codes = payload.get("exitCodes")
    if not isinstance(exit_codes, dict) or "0" not in exit_codes or "1" not in exit_codes:
        errors.append("status-contract:exitCodes")
    bound = payload.get("boundCommands")
    if not isinstance(bound, list) or "doctor" not in bound:
        errors.append("status-contract:boundCommands")
    exit_py = (root / "spell_sync" / "exit_codes.py").read_text(encoding="utf-8")
    for name in ("OK", "PUSH_ABORT", "LINT_FAILED", "UNKNOWN_COMMAND"):
        if name not in exit_py:
            errors.append(f"status-contract:exit_codes.py-missing:{name}")
    contracts_md = (root / "docs" / "CONTRACTS.md").read_text(encoding="utf-8")
    if "Evidence levels" not in contracts_md:
        errors.append("status-contract:docs/CONTRACTS.md-missing-Evidence-levels")
    if "Doctor / status exit codes" not in contracts_md:
        errors.append("status-contract:docs/CONTRACTS.md-missing-exit-table")
    return errors


def main(argv: list[str] | None = None) -> int:
    del argv
    errors = validate()
    if errors:
        print("STATUS_CONTRACT_VALIDATE: fail")
        for item in errors:
            print(f"  - {item}")
        return 1
    print("STATUS_CONTRACT_VALIDATE: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
