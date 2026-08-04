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

from scripts.execution_control.admission import assess_admission  # noqa: E402
from scripts.execution_control.history import HistoryStore  # noqa: E402
from scripts.execution_control.mappings import GATE_EXECUTION_IDS  # noqa: E402
from scripts.execution_control.registry import (  # noqa: E402
    REGISTRY_REL_PATH,
    load_registry,
    profile_for_execution_id,
)
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
        "--level",
        choices=("module", "cluster"),
        default="cluster",
        help="Module tests (edit loop) or cluster tests (full planner; dev-scope downgrades).",
    )
    parser.add_argument(
        "--dev-scope",
        action="store_true",
        help="Local minimal scope: shared fixtures map to test-selection only (no full fan-out).",
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


def build_timing_plan(plan, *, level: str, python: str) -> dict[str, object]:
    gate_key = "focused-module" if level == "module" else "focused-cluster"
    execution_id = GATE_EXECUTION_IDS[gate_key]
    registry = load_registry(ROOT / REGISTRY_REL_PATH)
    history = HistoryStore.open()
    profile = profile_for_execution_id(registry, execution_id)
    command = list(plan.command) if plan.command else [python, "-m", "pytest"]
    admission, timing_plan = assess_admission(
        ROOT,
        execution_id=execution_id,
        profile=profile,
        registry=registry,
        history=history,
        command=command,
        mode=level,
        required=False,
        test_file_count=len(plan.pytest_targets),
        test_node_count=0,
        cluster_ids=tuple(plan.clusters),
    )
    predicted = 0.0
    if timing_plan is not None:
        predicted = float(timing_plan.expected_seconds)
    return {
        "executionId": execution_id,
        "profileId": profile.profile_id,
        "testFileCount": len(plan.pytest_targets),
        "testNodeCount": 0,
        "clusterIds": list(plan.clusters),
        "coverage": False,
        "tui": False,
        "packaging": False,
        "predictedDurationSeconds": predicted,
        "admissionClass": admission.decision.value,
    }


def format_text(
    plan,
    *,
    explain: bool = False,
    level: str = "cluster",
    python: str = sys.executable,
) -> str:
    timing = build_timing_plan(plan, level=level, python=python)
    lines = [
        "TEST_PLAN_RESULT=success",
        f"TEST_PLAN_CHANGED_FILES={len(plan.changed_files)}",
        f"TEST_PLAN_CLUSTERS={','.join(plan.clusters)}",
        f"TEST_PLAN_TARGETS={len(plan.pytest_targets)}",
        f"TEST_PLAN_EXECUTION_ID={timing['executionId']}",
        f"TEST_PLAN_PROFILE={timing['profileId']}",
        f"TEST_PLAN_PREDICTED_SECONDS={timing['predictedDurationSeconds']}",
        f"TEST_PLAN_ADMISSION={timing['admissionClass']}",
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
        lines.append(f"TEST_PLAN_VALIDATION_LEVEL={plan.validation_level}")
        lines.append(
            f"TEST_PLAN_FINAL_FOCUSED_EVIDENCE={'true' if plan.final_focused_evidence else 'false'}"
        )
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
        level=args.level,
        python=args.python,
        dev_scope=args.dev_scope,
    )
    if args.format == "json":
        payload = plan.to_json_dict()
        payload["timing"] = build_timing_plan(plan, level=args.level, python=args.python)
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    else:
        sys.stdout.write(
            format_text(plan, explain=args.explain, level=args.level, python=args.python)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
