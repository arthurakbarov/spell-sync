#!/usr/bin/env python3
"""Run focused validation with deduplication via the executed-test ledger."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execution_control.gate_controller import GateController  # noqa: E402
from scripts.execution_control.mappings import GATE_EXECUTION_IDS  # noqa: E402
from scripts.execution_control.session import record_session_event  # noqa: E402
from scripts.test_plan import format_text  # noqa: E402
from scripts.test_selection.changes import collect_changed_files  # noqa: E402
from scripts.test_selection.ledger import StepResult, TestRunLedger  # noqa: E402
from scripts.test_selection.plan_steps import (  # noqa: E402
    PlannedStep,
    build_planned_steps,
    plan_metadata_signature,
)
from scripts.test_selection.planner import build_plan  # noqa: E402

FOCUSED_STEP_EXECUTION_IDS: dict[str, str] = {
    "validator": "focused:validators",
    "pytest": "focused:pytest",
    "ruff-check": "focused:static",
    "ruff-format": "focused:static",
    "mypy": "focused:static",
}


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


def _step_execution_id(step: PlannedStep) -> str:
    return FOCUSED_STEP_EXECUTION_IDS.get(step.kind, "focused:validators")


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
    gate_mode = "module" if args.level == "module" else "cluster"
    gate_id = GATE_EXECUTION_IDS["focused-module" if args.level == "module" else "focused-cluster"]
    if args.explain:
        sys.stdout.write(format_text(plan, explain=True))

    steps = build_planned_steps(
        plan,
        root=ROOT,
        python=args.python,
        changed_files=tuple(changed),
    )
    metadata = plan_metadata_signature(
        plan=plan,
        steps=steps,
        cluster_override=args.cluster,
        target_override=args.target,
    )
    if not steps and not plan.validators:
        print("TEST_RUN_RESULT=skipped")
        print("TEST_RUN_REASON=no-focused-targets")
        return 0

    ledger = TestRunLedger(ROOT)
    run_key = ledger.compute_key(steps=steps, metadata=metadata)

    if not args.force:
        existing = ledger.find_success(run_key=run_key, steps=steps, metadata=metadata)
        if existing is not None:
            print("TEST_RUN_RESULT=skipped")
            print("TEST_RUN_REASON=already-passed-for-current-state")
            print(f"TEST_RUN_KEY={run_key}")
            print(f"TEST_RUN_DURATION_SECONDS={existing.duration_seconds:.2f}")
            return 0

    test_file_count = len(plan.pytest_targets)
    gate_controller = GateController.open_gate_controller(ROOT)
    gate, state = gate_controller.begin_gate(
        execution_id=gate_id,
        command=[args.python, str(ROOT / "scripts" / "run_focused_tests.py")],
        mode=gate_mode,
        required=False,
        test_file_count=test_file_count,
    )
    if gate is None:
        return 0 if state == "reused" else 1

    started_at = datetime.now(timezone.utc)
    exit_code = 0
    step_results: list[StepResult] = []
    try:
        for step in steps:
            started = time.monotonic()
            execution_id = _step_execution_id(step)
            rc, timing = gate_controller.run_child(
                gate,
                child_execution_id=execution_id,
                command=list(step.argv),
                mode=gate_mode,
                required=False,
                cwd=ROOT,
                test_file_count=test_file_count,
            )
            duration = time.monotonic() - started
            if timing is None and rc == 0:
                record_session_event(
                    category="focused", duration_seconds=0.0, reused_saved=duration
                )
            else:
                record_session_event(category="focused", duration_seconds=duration)
            step_results.append(
                StepResult(
                    kind=step.kind,
                    command=list(step.argv),
                    exit_code=rc,
                    duration_seconds=duration,
                )
            )
            if rc != 0 or gate.stopped:
                exit_code = rc
                break
    finally:
        gate_controller.finish_gate(gate, exit_code=exit_code)

    completed_at = datetime.now(timezone.utc)
    duration = sum(step.duration_seconds for step in step_results)
    pytest_ran = any(step.kind == "pytest" for step in step_results)
    validator_count = sum(1 for step in step_results if step.kind == "validator")

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
            steps=steps,
            metadata=metadata,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            validation_level=plan.validation_level,
            final_focused_evidence=plan.final_focused_evidence,
            step_results=step_results,
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
