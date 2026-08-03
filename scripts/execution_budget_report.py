#!/usr/bin/env python3
"""Report execution budget history and predictions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execution_control.budget_analysis import (  # noqa: E402
    build_execution_budget_report,
    render_text_report,
    write_privacy_safe_execution_summary,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report execution budget history.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--execution-id", default=None)
    parser.add_argument("--window", default=None, help="Sample window, e.g. 30d")
    parser.add_argument("--edit-loop", action="store_true")
    parser.add_argument(
        "--write-summary",
        action="store_true",
        help="Write privacy-safe .artifacts/execution/execution-summary.json",
    )
    args = parser.parse_args(argv)
    payload = build_execution_budget_report(
        ROOT,
        execution_id=args.execution_id,
        window=args.window,
        edit_loop=args.edit_loop,
    )
    if args.write_summary:
        write_privacy_safe_execution_summary(ROOT, payload)
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(render_text_report(payload), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
