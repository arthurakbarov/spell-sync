#!/usr/bin/env python3
"""Local minimal validation (edit + commit gate) without coverage or admission blocks."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.cli_text import format_kv_lines  # noqa: E402
from scripts.execution_control.eta import announce_expected_eta  # noqa: E402
from scripts.execution_control.observe import (  # noqa: E402
    observe_subprocess,
    record_observation,
)
from scripts.test_selection.changes import collect_changed_files  # noqa: E402
from scripts.test_selection.planner import build_plan  # noqa: E402
from scripts.test_selection.registry import load_registry  # noqa: E402
from scripts.test_selection.sample_budget import apply_sample_budget  # noqa: E402

ARCHITECTURE_TRIGGERS = (
    "spell_sync/application/",
    "scripts/check_architecture.py",
)

# Strict local SLA targets (wall clock). Exceed → exit 2 after functional result.
L0_BUDGET_SECONDS = 60
L1_BUDGET_SECONDS = 120

STEP_HINTS = {
    "ruff-check": 3.0,
    "ruff-format": 3.0,
    "architecture": 8.0,
    "pytest": 20.0,
}


def budget_seconds_for_gate(gate: str) -> int:
    if gate == "L1":
        return L1_BUDGET_SECONDS
    return L0_BUDGET_SECONDS


def budget_status(*, wall_seconds: float, budget_seconds: int) -> str:
    return "within" if wall_seconds <= budget_seconds else "exceeded"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run local minimal validation (no coverage, outside edit-loop budget).",
    )
    parser.add_argument("--base", default="HEAD")
    parser.add_argument("--files", nargs="*", default=None)
    parser.add_argument("--cluster", default=None)
    parser.add_argument("--target", default=None)
    parser.add_argument(
        "--commit-gate",
        action="store_true",
        help="Commit gate: same affected module scope as default plus safety cluster tests.",
    )
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--explain", action="store_true")
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Print the planned steps/targets as JSON and exit without running them.",
    )
    parser.add_argument(
        "--ignore-budget",
        action="store_true",
        help="Do not fail when wall time exceeds the local minimal SLA (still report status).",
    )
    parser.add_argument(
        "--no-sample",
        action="store_true",
        help="Disable sample fill-to-budget on the L0 edit loop (must-keep only).",
    )
    return parser


def _run(argv: list[str], *, label: str) -> int:
    execution_id = f"dev-loop-step:{label}"
    hint = STEP_HINTS.get(label)
    if hint is None and label.startswith("validator:"):
        hint = 8.0
    print(f"DEV_LOOP_STEP={label}", flush=True)
    print(f"DEV_LOOP_COMMAND={' '.join(argv)}", flush=True)
    observed = observe_subprocess(
        root=ROOT,
        execution_id=execution_id,
        command=argv,
        expected_hint=hint,
        announce=True,
        print_result=False,
    )
    print(f"DEV_LOOP_STEP_EXIT={observed.exit_code}", flush=True)
    print(f"DEV_LOOP_STEP_SECONDS={observed.work_seconds:.2f}", flush=True)
    return int(observed.exit_code)


def _needs_architecture(changed: list[str]) -> bool:
    return any(
        path.startswith(prefix) or path == prefix.rstrip("/")
        for path in changed
        for prefix in ARCHITECTURE_TRIGGERS
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    gate = "L1" if args.commit_gate else "L0"
    budget = budget_seconds_for_gate(gate)
    wall_started = time.monotonic()
    gate_id = f"dev-loop:{gate}"
    if not args.plan:
        announce_expected_eta(
            gate_id,
            hint=float(budget),
            root=ROOT,
        )
    print(f"DEV_LOOP_GATE={gate}", flush=True)
    print("DEV_LOOP_COVERAGE=false", flush=True)
    print("DEV_LOOP_ADMISSION=bypass", flush=True)
    print(f"DEV_LOOP_BUDGET_SECONDS={budget}", flush=True)

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
        level="module",
        python=args.python,
        dev_scope=True,
        include_safety_cluster_tests=args.commit_gate,
    )
    pytest_targets = list(plan.pytest_targets)
    sample_meta: dict[str, object] | None = None
    sample_enabled = gate == "L0" and not args.no_sample and args.target is None
    if sample_enabled:
        registry = load_registry(ROOT / "tests" / "test-impact.toml")
        sample = apply_sample_budget(
            root=ROOT,
            registry=registry,
            must_keep_targets=pytest_targets,
            changed_files=list(plan.changed_files),
            budget_seconds=float(budget),
        )
        pytest_targets = list(sample.targets)
        sample_meta = sample.to_json_dict()
        print(
            format_kv_lines(
                [
                    ("DEV_LOOP_SAMPLE", "true"),
                    ("DEV_LOOP_SAMPLE_SEED", sample.seed),
                    ("DEV_LOOP_SAMPLE_MUST_KEEP", str(len(sample.must_keep))),
                    ("DEV_LOOP_SAMPLE_FILLED", str(len(sample.filled))),
                    ("DEV_LOOP_SAMPLE_OMITTED", str(len(sample.omitted))),
                    ("DEV_LOOP_SAMPLE_USED_SECONDS", str(sample.used_seconds)),
                    ("DEV_LOOP_SAMPLE_FILL_RATIO", str(sample.fill_ratio)),
                ]
            ),
            flush=True,
        )
    else:
        print("DEV_LOOP_SAMPLE=false", flush=True)

    print(f"DEV_LOOP_CHANGED_FILES={len(plan.changed_files)}")
    print(f"DEV_LOOP_CLUSTERS={','.join(plan.clusters)}")
    print(f"DEV_LOOP_TARGETS={len(pytest_targets)}")
    if args.explain or args.plan:
        for reason in plan.reasons:
            print(f"DEV_LOOP_REASON={reason}")
        for target in pytest_targets:
            print(f"DEV_LOOP_PYTEST_TARGET={target}")

    if args.plan:
        payload = {
            "gate": gate,
            "budgetSeconds": budget,
            "changedFiles": list(plan.changed_files),
            "clusters": list(plan.clusters),
            "validators": list(plan.validators),
            "pytestTargets": pytest_targets,
            "sample": sample_meta,
            "reasons": list(plan.reasons),
        }
        print("DEV_LOOP_PLAN_JSON_BEGIN", flush=True)
        print(json.dumps(payload, indent=2, sort_keys=True), flush=True)
        print("DEV_LOOP_PLAN_JSON_END", flush=True)
        print("DEV_LOOP_RESULT=plan", flush=True)
        print("DEV_LOOP_EXIT=0", flush=True)
        return 0

    exit_code = 0
    changed_py = sorted(
        path for path in plan.changed_files if path.endswith(".py") and (ROOT / path).is_file()
    )
    if changed_py:
        code = _run([args.python, "-m", "ruff", "check", *changed_py], label="ruff-check")
        exit_code = exit_code or code
        code = _run(
            [args.python, "-m", "ruff", "format", "--check", *changed_py],
            label="ruff-format",
        )
        exit_code = exit_code or code

    if _needs_architecture(list(plan.changed_files)):
        code = _run(
            [args.python, "scripts/check_architecture.py", "--check"],
            label="architecture",
        )
        exit_code = exit_code or code

    for validator in plan.validators:
        parts = validator.split()
        script = parts[0]
        rest = parts[1:]
        if script.endswith(".sh"):
            argv_cmd = ["bash", script, *rest]
        elif script.endswith(".py"):
            argv_cmd = [args.python, script, *rest]
        else:
            argv_cmd = [script, *rest]
        code = _run(argv_cmd, label=f"validator:{script}")
        exit_code = exit_code or code

    if pytest_targets:
        argv_cmd = [
            args.python,
            "-m",
            "pytest",
            *pytest_targets,
            "-q",
            "--durations=10",
        ]
        code = _run(argv_cmd, label="pytest")
        exit_code = exit_code or code
    else:
        print("DEV_LOOP_STEP=pytest")
        print("DEV_LOOP_STEP_SKIPPED=no-targets")

    wall_seconds = time.monotonic() - wall_started
    status = budget_status(wall_seconds=wall_seconds, budget_seconds=budget)
    record_observation(
        execution_id=gate_id,
        duration_seconds=wall_seconds,
        exit_code=exit_code,
        expected_seconds=float(budget),
        soft_seconds=float(budget),
    )

    print(f"DEV_LOOP_WALL_SECONDS={wall_seconds:.2f}")
    print(f"DEV_LOOP_BUDGET_STATUS={status}")
    if status == "exceeded" and not args.ignore_budget:
        print("DEV_LOOP_BUDGET_ACTION=shrink-scope")
        if exit_code == 0:
            exit_code = 2

    print(f"DEV_LOOP_RESULT={'success' if exit_code == 0 else 'failed'}")
    print(f"DEV_LOOP_EXIT={exit_code}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
