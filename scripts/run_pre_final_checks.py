#!/usr/bin/env python3
"""Pre-final gate: registry, Level 2 clusters, static checks, docs validators."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ci_history import summarize_ci_history  # noqa: E402
from scripts.execution_control.gate_flow import (  # noqa: E402
    gate_controller_for,
    open_gate_after_previews,
    preview_pre_final_child_plans,
    registry_for,
    run_bounded_planner,
)
from scripts.execution_control.mappings import GATE_EXECUTION_IDS  # noqa: E402
from scripts.execution_control.models import ExecutionStatus  # noqa: E402
from scripts.execution_control.session import record_session_event  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run pre-final validation gate.")
    parser.add_argument("--base", default="HEAD")
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args(argv)
    py = args.python
    gate_command = [py, str(ROOT / "scripts" / "run_pre_final_checks.py")]

    gate_controller = gate_controller_for(ROOT)
    registry = registry_for(ROOT)
    exit_code = 0
    terminal_status: ExecutionStatus | None = None
    plan_path = Path()
    gate = None

    try:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
            plan_path = Path(handle.name)
        planner_argv = [
            py,
            str(ROOT / "scripts" / "build_pre_final_plan.py"),
            "--base",
            args.base,
            "--python",
            py,
            "--output",
            str(plan_path),
        ]
        planner_rc, planner_state = run_bounded_planner(
            gate_controller,
            planner_execution_id="pre-final:planner",
            command=planner_argv,
            mode="pre-final",
            cwd=ROOT,
        )
        if planner_rc != 0:
            return planner_rc if planner_state != "reused" else 0

        payload = json.loads(plan_path.read_text(encoding="utf-8"))
        raw_steps = payload.get("steps", [])
        preview_steps = tuple(
            (str(item["name"]), [str(part) for part in item["command"]]) for item in raw_steps
        )
        child_plans = preview_pre_final_child_plans(
            ROOT,
            registry,
            steps=preview_steps,
            mode="pre-final",
        )
        gate, state, child_plans, _parent_plan = open_gate_after_previews(
            gate_controller,
            execution_id=GATE_EXECUTION_IDS["pre-final"],
            command=gate_command,
            mode="pre-final",
            child_plans=child_plans,
            required=False,
        )
        if gate is None:
            return 0 if state == "reused" else 1

        for item, child_plan in zip(raw_steps, child_plans, strict=True):
            if not gate_controller.check_orchestration_budget(gate):
                exit_code = 124
                break
            name = str(item["name"])
            command = [str(part) for part in item["command"]]
            started = time.monotonic()
            rc, execution = gate_controller.run_child_with_plan(
                gate,
                child_plan,
                command=command,
                cwd=ROOT,
            )
            duration = time.monotonic() - started
            if execution is None and rc == 0:
                record_session_event(
                    category="pre-final", duration_seconds=0.0, reused_saved=duration
                )
            else:
                record_session_event(category="pre-final", duration_seconds=duration)
            print(f"PRE_FINAL_STEP={name} exit={rc} duration={duration:.2f}s")
            if rc != 0 or gate.stopped:
                exit_code = rc
                break
    except KeyboardInterrupt:
        exit_code = 130
        terminal_status = ExecutionStatus.INTERRUPTED
        raise
    finally:
        if plan_path:
            plan_path.unlink(missing_ok=True)
        if gate is not None:
            gate_controller.finish_gate(gate, exit_code=exit_code, status=terminal_status)

    counts = summarize_ci_history(ROOT / ".artifacts" / "ci").to_json_dict()
    print(f"PRE_FINAL_RESULT={'success' if exit_code == 0 else 'failed'}")
    print(f"PRE_FINAL_EXIT={exit_code}")
    print(f"fullCiAttempts={counts['fullCiAttempts']}")
    print(f"fullCiFailures={counts['fullCiFailures']}")
    print(f"fullCiSuccesses={counts['fullCiSuccesses']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
