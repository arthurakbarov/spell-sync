#!/usr/bin/env python3
"""Run focused validation with deduplication via the executed-test ledger."""

from __future__ import annotations

import argparse
import shlex
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
from scripts.test_selection.ledger import StepResult, TestRunLedger  # noqa: E402
from scripts.test_selection.planner import TestPlan, build_plan  # noqa: E402


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run focused tests selected for current changes.",
    )
    parser.add_argument("--base", default="HEAD")
    parser.add_argument("--cluster", default=None)
    parser.add_argument("--target", default=None)
    parser.add_argument("--level", choices=("module", "cluster"), default="cluster")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--explain", action="store_true")
    parser.add_argument("--python", default=sys.executable)
    return parser


def run_command(command: list[str], *, cwd: Path) -> tuple[int, float]:
    started = time.monotonic()
    proc = subprocess.run(command, cwd=cwd)
    duration = time.monotonic() - started
    return proc.returncode, duration


def _split_validator(spec: str) -> list[str]:
    if spec.endswith(".sh"):
        return ["bash", spec]
    return shlex.split(spec)


def _execute_plan(plan: TestPlan, *, cwd: Path) -> tuple[int, list[StepResult]]:
    steps: list[StepResult] = []
    for validator in plan.validators:
        command = _split_validator(validator)
        if command[0].endswith(".py") and not Path(command[0]).is_absolute():
            command = [sys.executable, *command]
        exit_code, duration = run_command(command, cwd=cwd)
        steps.append(
            StepResult(
                kind="validator",
                command=command,
                exit_code=exit_code,
                duration_seconds=duration,
            )
        )
        if exit_code != 0:
            return exit_code, steps

    for target in plan.static_targets:
        for kind, args in (
            ("ruff", [sys.executable, "-m", "ruff", "check", target]),
            ("ruff", [sys.executable, "-m", "ruff", "format", "--check", target]),
        ):
            exit_code, duration = run_command(args, cwd=cwd)
            steps.append(
                StepResult(
                    kind=kind,
                    command=args,
                    exit_code=exit_code,
                    duration_seconds=duration,
                )
            )
            if exit_code != 0:
                return exit_code, steps

    if plan.pytest_targets:
        command = list(plan.command)
        exit_code, duration = run_command(command, cwd=cwd)
        steps.append(
            StepResult(
                kind="pytest",
                command=command,
                exit_code=exit_code,
                duration_seconds=duration,
            )
        )
        if exit_code != 0:
            return exit_code, steps

    return 0, steps


def _plan_signature(plan: TestPlan) -> tuple[list[str], list[str], list[str]]:
    command_parts: list[str] = []
    if plan.command:
        command_parts.extend(plan.command)
    for validator in plan.validators:
        command_parts.extend(_split_validator(validator))
    return (
        command_parts,
        list(plan.pytest_targets),
        list(plan.clusters),
    )


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
        level=args.level,
        python=args.python,
    )
    if args.explain:
        sys.stdout.write(format_text(plan, explain=True))

    command_parts, targets, clusters = _plan_signature(plan)
    if not command_parts and not plan.validators:
        print("TEST_RUN_RESULT=skipped")
        print("TEST_RUN_REASON=no-focused-targets")
        return 0

    ledger = TestRunLedger(ROOT)
    run_key = ledger.compute_key(command=command_parts, targets=targets, clusters=clusters)

    if not args.force:
        existing = ledger.find_success(
            run_key=run_key,
            command=command_parts,
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
    exit_code, steps = _execute_plan(plan, cwd=ROOT)
    completed_at = datetime.now(timezone.utc)
    duration = sum(step.duration_seconds for step in steps)

    pytest_ran = any(step.kind == "pytest" for step in steps)
    validator_count = sum(1 for step in steps if step.kind == "validator")

    print(f"TEST_RUN_RESULT={'success' if exit_code == 0 else 'failed'}")
    print(f"TEST_RUN_EXIT={exit_code}")
    print(f"TEST_RUN_KEY={run_key}")
    print(f"TEST_RUN_DURATION_SECONDS={duration:.2f}")
    print(f"TEST_RUN_PYTEST={'ran' if pytest_ran else 'skipped'}")
    print(f"TEST_RUN_VALIDATORS={validator_count}")
    if plan.command:
        print(f"TEST_RUN_COMMAND={' '.join(plan.command)}")

    if exit_code == 0:
        ledger.record_success(
            run_key=run_key,
            command=command_parts,
            targets=targets,
            clusters=clusters,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            validation_level=plan.validation_level,
            final_focused_evidence=plan.final_focused_evidence,
            steps=steps,
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
