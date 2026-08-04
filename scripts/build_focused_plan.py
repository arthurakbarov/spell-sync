#!/usr/bin/env python3
"""Build a bounded focused-test plan as JSON for supervised gate planning."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.test_selection.changes import collect_changed_files  # noqa: E402
from scripts.test_selection.digest import tree_digest  # noqa: E402
from scripts.test_selection.ledger import TestRunLedger  # noqa: E402
from scripts.test_selection.plan_steps import (  # noqa: E402
    PlannedStep,
    build_planned_steps,
    plan_metadata_signature,
)
from scripts.test_selection.planner import build_plan  # noqa: E402


def _steps_to_json(steps: tuple[PlannedStep, ...]) -> list[dict[str, object]]:
    return [{"kind": step.kind, "argv": list(step.argv)} for step in steps]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build focused validation plan JSON.")
    parser.add_argument("--base", default="HEAD")
    parser.add_argument("--cluster", default=None)
    parser.add_argument("--target", default=None)
    parser.add_argument("--level", choices=("module", "cluster"), default="cluster")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sleep", type=float, default=0.0, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.sleep > 0:
        time.sleep(args.sleep)

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
    steps = build_planned_steps(
        plan,
        python=args.python,
        changed_files=tuple(changed),
    )
    metadata = plan_metadata_signature(
        plan=plan,
        steps=steps,
        cluster_override=args.cluster,
        target_override=args.target,
    )
    ledger = TestRunLedger(ROOT)
    run_key = ledger.compute_key(steps=steps, metadata=metadata)
    payload = {
        "schemaVersion": 1,
        "plan": plan.to_json_dict(),
        "steps": _steps_to_json(steps),
        "metadata": list(metadata),
        "runKey": run_key,
        "treeDigest": tree_digest(ROOT),
        "testFileCount": len(plan.pytest_targets),
        "gateMode": "module" if args.level == "module" else "cluster",
        "explainOnly": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"FOCUSED_PLAN_OUTPUT={args.output}")
    print(f"FOCUSED_PLAN_STEPS={len(steps)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
