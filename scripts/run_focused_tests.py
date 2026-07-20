#!/usr/bin/env python3
"""Run focused validation with deduplication via the executed-test ledger."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.test_plan import format_text  # noqa: E402
from scripts.test_selection.changes import collect_changed_files  # noqa: E402
from scripts.test_selection.ledger import TestRunLedger  # noqa: E402
from scripts.test_selection.planner import build_plan  # noqa: E402


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run focused tests selected for current changes.",
    )
    parser.add_argument("--base", default="HEAD")
    parser.add_argument("--cluster", default=None)
    parser.add_argument("--target", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--explain", action="store_true")
    parser.add_argument("--python", default=sys.executable)
    return parser


def run_command(command: list[str], *, cwd: Path) -> tuple[int, float]:
    started = time.monotonic()
    proc = subprocess.run(command, cwd=cwd)
    duration = time.monotonic() - started
    return proc.returncode, duration


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    changed = collect_changed_files(
        ROOT,
        base=None if args.base == "HEAD" else args.base,
    )
    plan = build_plan(
        ROOT,
        changed,
        cluster_override=args.cluster,
        target_override=args.target,
        python=args.python,
    )
    if args.explain:
        sys.stdout.write(format_text(plan, explain=True))

    if not plan.command:
        print("TEST_RUN_RESULT=skipped")
        print("TEST_RUN_REASON=no-pytest-targets")
        return 0

    command = list(plan.command)
    targets = list(plan.pytest_targets)
    clusters = list(plan.clusters)
    ledger = TestRunLedger(ROOT)
    run_key = ledger.compute_key(command=command, targets=targets, clusters=clusters)

    if not args.force:
        existing = ledger.find_success(
            run_key=run_key,
            command=command,
            targets=targets,
            clusters=clusters,
        )
        if existing is not None:
            print("TEST_RUN_RESULT=skipped")
            print("TEST_RUN_REASON=already-passed-for-current-state")
            print(f"TEST_RUN_KEY={run_key}")
            print(f"TEST_RUN_DURATION_SECONDS={existing.duration_seconds:.2f}")
            return 0

    started_at = datetime.now(timezone.utc)
    exit_code, duration = run_command(command, cwd=ROOT)
    completed_at = datetime.now(timezone.utc)

    print(f"TEST_RUN_RESULT={'success' if exit_code == 0 else 'failed'}")
    print(f"TEST_RUN_EXIT={exit_code}")
    print(f"TEST_RUN_KEY={run_key}")
    print(f"TEST_RUN_DURATION_SECONDS={duration:.2f}")
    print(f"TEST_RUN_COMMAND={' '.join(command)}")

    if exit_code == 0:
        ledger.record_success(
            run_key=run_key,
            command=command,
            targets=targets,
            clusters=clusters,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
