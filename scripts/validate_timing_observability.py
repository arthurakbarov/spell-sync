#!/usr/bin/env python3
"""Validate timing observability report contracts."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execution_control.budget_analysis import (  # noqa: E402
    REPORT_SCHEMA_VERSION,
    build_execution_budget_report,
    write_privacy_safe_execution_summary,
)
from scripts.test_groups import validate_union  # noqa: E402


def main() -> int:
    payload = build_execution_budget_report(ROOT, edit_loop=True)
    if payload.get("schemaVersion") != REPORT_SCHEMA_VERSION:
        print("TIMING_OBSERVABILITY_VALIDATION=failed")
        print("TIMING_OBSERVABILITY_FAILED_ID=schema-version")
        return 1
    if "editLoopSummary" not in payload:
        print("TIMING_OBSERVABILITY_VALIDATION=failed")
        print("TIMING_OBSERVABILITY_FAILED_ID=edit-loop-summary-missing")
        return 1
    ok, problems = validate_union(ROOT)
    if not ok:
        print("TIMING_OBSERVABILITY_VALIDATION=failed")
        print("TIMING_OBSERVABILITY_FAILED_ID=test-group-union")
        for item in problems[:5]:
            print(f"TIMING_OBSERVABILITY_DETAIL={item}")
        return 1
    summary_path = write_privacy_safe_execution_summary(ROOT, payload)
    raw = summary_path.read_text(encoding="utf-8")
    forbidden = ("HOME", "tests/", "python -m", "/Users/")
    for token in forbidden:
        if token in raw:
            print("TIMING_OBSERVABILITY_VALIDATION=failed")
            print(f"TIMING_OBSERVABILITY_FAILED_ID=privacy-leak:{token}")
            return 1
    print("TIMING_OBSERVABILITY_VALIDATION=success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
