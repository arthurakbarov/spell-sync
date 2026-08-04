#!/usr/bin/env python3
"""Build a bounded pre-final plan as JSON for supervised gate planning."""

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
from scripts.test_selection.planner import build_plan  # noqa: E402

POLISH_VALIDATORS: tuple[tuple[str, str], ...] = (
    ("timing-observability", "scripts/validate_timing_observability.py"),
    ("dependency-groups", "scripts/validate_dependency_groups.py"),
    ("support-matrix", "scripts/validate_support_matrix.py"),
    ("snapshot-policy", "scripts/validate_snapshot_policy.py"),
    ("user-documentation", "scripts/validate_user_documentation.py"),
    ("repository-consistency", "scripts/validate_repository_consistency.py"),
    ("dead-code-audit", "scripts/audit_dead_code.py"),
)


def _changed_python_files(changed: list[str]) -> list[str]:
    return sorted(path for path in changed if path.endswith(".py") and (ROOT / path).is_file())


def _changed_production_modules(changed: list[str]) -> list[str]:
    return sorted(
        path
        for path in changed
        if path.startswith("spell_sync/") and path.endswith(".py") and (ROOT / path).is_file()
    )


def _build_steps(changed: list[str], plan, *, py: str) -> list[dict[str, object]]:
    steps: list[tuple[str, list[str]]] = [
        ("registry", [py, "scripts/validate_test_impact.py"]),
    ]
    if plan.pytest_targets:
        steps.append(("focused-pytest", [py, "-m", "pytest", *plan.pytest_targets, "-q"]))
    for validator in plan.validators:
        if validator.endswith(".sh"):
            steps.append((f"validator:{validator}", ["bash", validator]))
        else:
            parts = validator.split()
            steps.append((f"validator:{parts[0]}", [py, *parts]))
    for path in _changed_python_files(changed):
        steps.append((f"ruff-check:{path}", [py, "-m", "ruff", "check", path]))
        steps.append((f"ruff-format:{path}", [py, "-m", "ruff", "format", "--check", path]))
    for module in _changed_production_modules(changed):
        pkg_path = str(Path(module).parent)
        mypy_target = pkg_path if module.endswith("__init__.py") else module
        steps.append((f"mypy:{module}", [py, "-m", "mypy", mypy_target]))
    docs_validators = [
        "scripts/check-docs-style.sh",
        "scripts/check_docs_contract.py",
    ]
    if any(path.startswith(".cursor/") or "AGENT" in path.upper() for path in changed):
        docs_validators.append("scripts/check_agent_config.py")
    for validator in docs_validators:
        if validator.endswith(".sh"):
            steps.append((validator, ["bash", validator]))
        else:
            steps.append((validator, [py, validator]))
    for name, validator in POLISH_VALIDATORS:
        steps.append((f"polish:{name}", [py, validator]))
    return [{"name": name, "command": command} for name, command in steps]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build pre-final validation plan JSON.")
    parser.add_argument("--base", default="HEAD")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sleep", type=float, default=0.0, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.sleep > 0:
        time.sleep(args.sleep)

    changed = collect_changed_files(ROOT, base=None if args.base == "HEAD" else args.base)
    plan = build_plan(ROOT, changed, level="cluster", python=args.python)
    payload = {
        "schemaVersion": 1,
        "plan": plan.to_json_dict(),
        "steps": _build_steps(changed, plan, py=args.python),
        "changedFiles": changed,
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"PRE_FINAL_PLAN_OUTPUT={args.output}")
    print(f"PRE_FINAL_PLAN_STEPS={len(payload['steps'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
