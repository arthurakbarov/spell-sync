#!/usr/bin/env python3
"""Local administration for execution history samples."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execution_control.history import HistoryStore  # noqa: E402


def _validate_reason(reason: str) -> str:
    cleaned = reason.strip()
    if not cleaned or len(cleaned) > 200:
        raise ValueError("reason must be 1-200 characters")
    for sentinel in ("/Users/", "/home/", "secret", "token", "password"):
        if sentinel.lower() in cleaned.lower():
            raise ValueError("reason must not contain private paths or secrets")
    return cleaned


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Administer execution history samples.")
    sub = parser.add_subparsers(dest="command", required=True)
    accept = sub.add_parser("accept-sample")
    accept.add_argument("run_id")
    accept.add_argument("--reason", required=True)
    reject = sub.add_parser("reject-sample")
    reject.add_argument("run_id")
    reject.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    reason = _validate_reason(args.reason)
    history = HistoryStore.open()
    if args.command == "accept-sample":
        ok = history.accept_sample(args.run_id, reason)
        print("EXECUTION_ADMIN_ACTION=accept-sample")
    else:
        ok = history.reject_sample(args.run_id, reason)
        print("EXECUTION_ADMIN_ACTION=reject-sample")
    if not ok:
        print("EXECUTION_ADMIN_RESULT=failed")
        return 1
    print("EXECUTION_ADMIN_RESULT=success")
    print(f"EXECUTION_ADMIN_RUN_ID={args.run_id}")
    print(f"EXECUTION_ADMIN_REASON={reason}")
    print(f"EXECUTION_HISTORY_DEGRADED={'true' if history.degraded else 'false'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
