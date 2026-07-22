#!/usr/bin/env python3
"""Pre-final gate: registry, Level 2 clusters, static checks, docs validators."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ci_history import summarize_ci_history  # noqa: E402
from scripts.execution_control.gate_controller import GateController  # noqa: E402
from scripts.execution_control.mappings import GATE_EXECUTION_IDS  # noqa: E402
from scripts.execution_control.session import record_session_event  # noqa: E402
from scripts.test_selection.changes import collect_changed_files  # noqa: E402
from scripts.test_selection.planner import build_plan  # noqa: E402


def _changed_python_files(changed: list[str]) -> list[str]:
    return sorted(path for path in changed if path.endswith(".py"))


def _changed_production_modules(changed: list[str]) -> list[str]:
    return sorted(
        path for path in changed if path.startswith("spell_sync/") and path.endswith(".py")
    )


def _step_execution_id(name: str) -> str:
    if name == "registry":
        return "pre-final:validators"
    if name.startswith("validator:"):
        return "pre-final:validators"
    if name.startswith("focused-pytest") or name == "focused-pytest":
        return "pre-final:pytest"
    if name.startswith("ruff-check:"):
        return "pre-final:ruff-check"
    if name.startswith("ruff-format:"):
        return "pre-final:ruff-format"
    if name.startswith("mypy:"):
        return "pre-final:mypy"
    if name.endswith(".sh") or name.endswith(".py"):
        return "pre-final:validators"
    return "pre-final:validators"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run pre-final validation gate.")
    parser.add_argument("--base", default="HEAD")
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args(argv)
    py = args.python
    changed = collect_changed_files(ROOT, base=None if args.base == "HEAD" else args.base)
    plan = build_plan(ROOT, changed, level="cluster", python=py)

    steps: list[tuple[str, list[str]]] = [
        ("registry", [py, "scripts/validate_test_impact.py"]),
    ]
    if plan.pytest_targets:
        steps.append(
            (
                "focused-pytest",
                [
                    py,
                    "-m",
                    "pytest",
                    *plan.pytest_targets,
                    "-q",
                ],
            )
        )
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
        "scripts/check-docs-contract.py",
    ]
    if any(path.startswith(".cursor/") or "AGENT" in path.upper() for path in changed):
        docs_validators.append("scripts/check-agent-config.py")
    for validator in docs_validators:
        if validator.endswith(".sh"):
            steps.append((validator, ["bash", validator]))
        else:
            steps.append((validator, [py, validator]))

    gate_controller = GateController.open_gate_controller(ROOT)
    gate, state = gate_controller.begin_gate(
        execution_id=GATE_EXECUTION_IDS["pre-final"],
        command=[py, str(ROOT / "scripts" / "run_pre_final_checks.py")],
        mode="pre-final",
        required=False,
    )
    if gate is None:
        return 0 if state == "reused" else 1

    exit_code = 0
    try:
        for name, command in steps:
            started = time.monotonic()
            execution_id = _step_execution_id(name)
            rc, timing = gate_controller.run_child(
                gate,
                child_execution_id=execution_id,
                command=command,
                mode="pre-final",
                required=False,
                cwd=ROOT,
            )
            duration = time.monotonic() - started
            if timing is None and rc == 0:
                record_session_event(
                    category="pre-final", duration_seconds=0.0, reused_saved=duration
                )
            else:
                record_session_event(category="pre-final", duration_seconds=duration)
            print(f"PRE_FINAL_STEP={name} exit={rc} duration={duration:.2f}s")
            if rc != 0 or gate.stopped:
                exit_code = rc
                break
    finally:
        gate_controller.finish_gate(gate, exit_code=exit_code)

    counts = summarize_ci_history(ROOT / ".artifacts" / "ci").to_json_dict()
    print(f"PRE_FINAL_RESULT={'success' if exit_code == 0 else 'failed'}")
    print(f"PRE_FINAL_EXIT={exit_code}")
    print(f"fullCiAttempts={counts['fullCiAttempts']}")
    print(f"fullCiFailures={counts['fullCiFailures']}")
    print(f"fullCiSuccesses={counts['fullCiSuccesses']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
