#!/usr/bin/env python3
"""Pre-final gate: registry, Level 2 clusters, static checks, docs validators."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.test_selection.changes import collect_changed_files  # noqa: E402
from scripts.test_selection.planner import build_plan  # noqa: E402


def _run(command: list[str], *, cwd: Path) -> tuple[int, float]:
    started = time.monotonic()
    proc = subprocess.run(command, cwd=cwd)
    return proc.returncode, time.monotonic() - started


def _changed_python_files(changed: list[str]) -> list[str]:
    return sorted(path for path in changed if path.endswith(".py"))


def _changed_production_modules(changed: list[str]) -> list[str]:
    return sorted(
        path for path in changed if path.startswith("spell_sync/") and path.endswith(".py")
    )


from scripts.ci_history import summarize_ci_history  # noqa: E402


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

    exit_code = 0
    for name, command in steps:
        rc, duration = _run(command, cwd=ROOT)
        print(f"PRE_FINAL_STEP={name} exit={rc} duration={duration:.2f}s")
        if rc != 0:
            exit_code = rc

    counts = summarize_ci_history(ROOT / ".artifacts" / "ci").to_json_dict()
    print(f"PRE_FINAL_RESULT={'success' if exit_code == 0 else 'failed'}")
    print(f"PRE_FINAL_EXIT={exit_code}")
    print(f"fullCiAttempts={counts['fullCiAttempts']}")
    print(f"fullCiFailures={counts['fullCiFailures']}")
    print(f"fullCiSuccesses={counts['fullCiSuccesses']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
