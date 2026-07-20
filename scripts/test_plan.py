#!/usr/bin/env python3
"""Change-aware test planner for spell-sync development."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.test_selection.changes import collect_changed_files  # noqa: E402
from scripts.test_selection.planner import build_plan  # noqa: E402


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan focused validation for current repository changes.",
    )
    parser.add_argument(
        "--base",
        default="HEAD",
        help="Git base for committed diff (default: working tree changes only).",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=None,
        help="Explicit changed files instead of git detection.",
    )
    parser.add_argument(
        "--cluster",
        default=None,
        help="Force a specific risk cluster.",
    )
    parser.add_argument(
        "--target",
        default=None,
        help="Force a specific pytest target.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Include detailed reasons in text output.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python interpreter for planned pytest command.",
    )
    return parser


def format_text(plan, *, explain: bool = False) -> str:
    lines = [
        "TEST_PLAN_RESULT=success",
        f"TEST_PLAN_CHANGED_FILES={len(plan.changed_files)}",
        f"TEST_PLAN_CLUSTERS={','.join(plan.clusters)}",
        f"TEST_PLAN_TARGETS={len(plan.pytest_targets)}",
    ]
    if plan.command:
        lines.append(f"TEST_PLAN_COMMAND={' '.join(plan.command)}")
    else:
        lines.append("TEST_PLAN_COMMAND=")
    if plan.reasons:
        lines.append(f"TEST_PLAN_REASON={plan.reasons[0]}")
    if explain:
        for reason in plan.reasons:
            lines.append(f"TEST_PLAN_REASON_DETAIL={reason}")
        for target in plan.pytest_targets:
            lines.append(f"TEST_PLAN_PYTEST_TARGET={target}")
        for validator in plan.validators:
            lines.append(f"TEST_PLAN_VALIDATOR={validator}")
        lines.append(f"TEST_PLAN_REQUIRES_FULL_CI={'true' if plan.requires_full_ci else 'false'}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    changed = collect_changed_files(
        ROOT,
        base=None if args.base == "HEAD" else args.base,
        explicit_files=args.files,
    )
    plan = build_plan(
        ROOT,
        changed,
        cluster_override=args.cluster,
        target_override=args.target,
        python=args.python,
    )
    if args.format == "json":
        sys.stdout.write(json.dumps(plan.to_json_dict(), indent=2) + "\n")
    else:
        sys.stdout.write(format_text(plan, explain=args.explain))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
