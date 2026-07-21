"""Canonical executable steps for focused validation plans."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path

from scripts.test_selection.planner import PLAN_SCHEMA_VERSION, TestPlan


@dataclass(frozen=True, slots=True)
class PlannedStep:
    kind: str
    argv: tuple[str, ...]


def _split_validator(spec: str) -> tuple[str, ...]:
    if spec.endswith(".sh"):
        return ("bash", spec)
    return tuple(shlex.split(spec))


def _dedupe_steps(steps: list[PlannedStep]) -> tuple[PlannedStep, ...]:
    seen: set[tuple[str, tuple[str, ...]]] = set()
    ordered: list[PlannedStep] = []
    for step in steps:
        key = (step.kind, step.argv)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(step)
    return tuple(ordered)


def build_planned_steps(
    plan: TestPlan,
    *,
    root: Path,
    python: str,
    changed_files: tuple[str, ...] = (),
) -> tuple[PlannedStep, ...]:
    del root
    steps: list[PlannedStep] = []

    for validator in plan.validators:
        argv = _split_validator(validator)
        if argv and argv[0].endswith(".py"):
            argv = (python, *argv)
        steps.append(PlannedStep(kind="validator", argv=argv))

    for target in plan.static_targets:
        steps.append(
            PlannedStep(
                kind="ruff-check",
                argv=(python, "-m", "ruff", "check", target),
            )
        )
        steps.append(
            PlannedStep(
                kind="ruff-format",
                argv=(python, "-m", "ruff", "format", "--check", target),
            )
        )

    changed_py = sorted(path for path in changed_files if path.endswith(".py"))
    for path in changed_py:
        if path not in plan.static_targets:
            steps.append(
                PlannedStep(
                    kind="ruff-check",
                    argv=(python, "-m", "ruff", "check", path),
                )
            )
            steps.append(
                PlannedStep(
                    kind="ruff-format",
                    argv=(python, "-m", "ruff", "format", "--check", path),
                )
            )

    production_modules = sorted(
        path for path in changed_py if path.startswith("spell_sync/") and path.endswith(".py")
    )
    for module in production_modules:
        mypy_target = str(Path(module).parent) if module.endswith("__init__.py") else module
        steps.append(
            PlannedStep(
                kind="mypy",
                argv=(python, "-m", "mypy", mypy_target),
            )
        )

    if plan.pytest_targets and plan.command:
        steps.append(PlannedStep(kind="pytest", argv=tuple(plan.command)))

    return _dedupe_steps(steps)


def plan_metadata_signature(
    *,
    plan: TestPlan,
    steps: tuple[PlannedStep, ...],
    cluster_override: str | None = None,
    target_override: str | None = None,
) -> tuple[str, ...]:
    parts = [
        f"schema={PLAN_SCHEMA_VERSION}",
        f"level={plan.validation_level}",
        f"clusters={'|'.join(plan.clusters)}",
        f"required={'|'.join(plan.required_clusters)}",
    ]
    if cluster_override:
        parts.append(f"clusterOverride={cluster_override}")
    if target_override:
        parts.append(f"targetOverride={target_override}")
    for step in steps:
        parts.append(f"{step.kind}:{' '.join(step.argv)}")
    return tuple(parts)
