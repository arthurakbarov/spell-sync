#!/usr/bin/env python3
"""Run focused validation with deduplication via the executed-test ledger."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execution_control.gate_previews import (  # noqa: E402
    gate_controller_for,
    open_gate_after_previews,
    preview_focused_child_plans,
    registry_for,
    run_bounded_planner,
)
from scripts.execution_control.mappings import GATE_EXECUTION_IDS  # noqa: E402
from scripts.execution_control.models import ExecutionStatus  # noqa: E402
from scripts.execution_control.session import record_session_event  # noqa: E402
from scripts.test_selection.ledger import StepResult, TestRunLedger  # noqa: E402
from scripts.test_selection.plan_steps import PlannedStep  # noqa: E402


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


def _load_planned_payload(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    gate_mode = "module" if args.level == "module" else "cluster"
    gate_id = GATE_EXECUTION_IDS["focused-module" if args.level == "module" else "focused-cluster"]
    gate_command = [args.python, str(ROOT / "scripts" / "run_focused_tests.py")]

    gate_controller = gate_controller_for(ROOT)
    registry = registry_for(ROOT)
    exit_code = 0
    terminal_status: ExecutionStatus | None = None
    started_at = datetime.now(timezone.utc)
    step_results: list[StepResult] = []
    plan_payload: dict[str, object] | None = None
    run_key = ""
    metadata: tuple[str, ...] = ()
    steps: tuple[PlannedStep, ...] = ()
    plan_path = Path()
    gate = None
    child_plans: tuple = ()

    try:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
            plan_path = Path(handle.name)
        planner_argv = [
            args.python,
            str(ROOT / "scripts" / "build_focused_plan.py"),
            "--base",
            args.base,
            "--level",
            args.level,
            "--python",
            args.python,
            "--output",
            str(plan_path),
        ]
        if args.cluster:
            planner_argv.extend(["--cluster", args.cluster])
        if args.target:
            planner_argv.extend(["--target", args.target])

        planner_rc, planner_state = run_bounded_planner(
            gate_controller,
            planner_execution_id="focused:planner",
            command=planner_argv,
            mode=gate_mode,
            cwd=ROOT,
        )
        if planner_rc != 0 and planner_state != "reused":
            return planner_rc

        # Reused planner admission skips the subprocess, so the ephemeral --output
        # path stays empty. Materialize the plan so downstream steps can load it.
        if planner_state == "reused" or not plan_path.is_file() or plan_path.stat().st_size == 0:
            direct = subprocess.run(planner_argv, cwd=ROOT, check=False)
            if direct.returncode != 0:
                return direct.returncode

        plan_payload = _load_planned_payload(plan_path)
        if args.explain:
            sys.stdout.write(json.dumps(plan_payload.get("plan", {}), indent=2) + "\n")
        metadata = tuple(str(item) for item in plan_payload.get("metadata", ()))
        run_key = str(plan_payload.get("runKey", ""))
        test_file_count = int(plan_payload.get("testFileCount", 0))
        steps = tuple(
            PlannedStep(kind=str(item["kind"]), argv=tuple(str(part) for part in item["argv"]))
            for item in plan_payload.get("steps", [])
        )
        if not steps and not plan_payload.get("plan", {}).get("validators"):
            print("TEST_RUN_RESULT=skipped")
            print("TEST_RUN_REASON=no-focused-targets")
            return 0

        ledger = TestRunLedger(ROOT)
        if not args.force:
            existing = ledger.find_success(run_key=run_key, steps=steps, metadata=metadata)
            if existing is not None:
                print("TEST_RUN_RESULT=skipped")
                print("TEST_RUN_REASON=already-passed-for-current-state")
                print(f"TEST_RUN_KEY={run_key}")
                print(f"TEST_RUN_DURATION_SECONDS={existing.duration_seconds:.2f}")
                record_session_event(
                    category="focused",
                    duration_seconds=0.0,
                    reused_saved=float(existing.duration_seconds),
                )
                return 0

        preview_steps = tuple((step.kind, list(step.argv)) for step in steps)
        child_plans = preview_focused_child_plans(
            ROOT,
            registry,
            steps=preview_steps,
            mode=gate_mode,
            test_file_count=test_file_count,
        )
        gate, state, child_plans, _parent_plan = open_gate_after_previews(
            gate_controller,
            execution_id=gate_id,
            command=gate_command,
            mode=gate_mode,
            child_plans=child_plans,
            required=False,
            test_file_count=test_file_count,
        )
        if gate is None:
            return 0 if state == "reused" else 1

        for step, child_plan in zip(steps, child_plans, strict=True):
            if not gate_controller.check_orchestration_budget(gate):
                exit_code = 124
                break
            started = time.monotonic()
            rc, _execution = gate_controller.run_child_with_plan(
                gate,
                child_plan,
                command=list(step.argv),
                cwd=ROOT,
            )
            duration = time.monotonic() - started
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

        if exit_code == 0 and plan_payload is not None:
            completed_at = datetime.now(timezone.utc)
            duration = sum(step.duration_seconds for step in step_results)
            plan = plan_payload["plan"]
            ledger.record_success(
                run_key=run_key,
                steps=steps,
                metadata=metadata,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
                validation_level=int(plan.get("validationLevel", 0)),
                final_focused_evidence=bool(plan.get("finalFocusedEvidence", False)),
                step_results=step_results,
            )
    except KeyboardInterrupt:
        exit_code = 130
        terminal_status = ExecutionStatus.INTERRUPTED
        raise
    finally:
        if plan_path:
            plan_path.unlink(missing_ok=True)
        if gate is not None:
            gate_controller.finish_gate(gate, exit_code=exit_code, status=terminal_status)

    if step_results:
        duration = sum(step.duration_seconds for step in step_results)
        pytest_ran = any(step.kind == "pytest" for step in step_results)
        validator_count = sum(1 for step in step_results if step.kind == "validator")
        print(f"TEST_RUN_RESULT={'success' if exit_code == 0 else 'failed'}")
        print(f"TEST_RUN_EXIT={exit_code}")
        print(f"TEST_RUN_KEY={run_key}")
        print(f"TEST_RUN_DURATION_SECONDS={duration:.2f}")
        print(f"TEST_RUN_PYTEST={'ran' if pytest_ran else 'skipped'}")
        print(f"TEST_RUN_VALIDATORS={validator_count}")
        if plan_payload and plan_payload.get("plan", {}).get("command"):
            print(f"TEST_RUN_COMMAND={' '.join(plan_payload['plan']['command'])}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
