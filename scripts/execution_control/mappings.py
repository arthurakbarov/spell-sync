"""Stable execution ID mappings for integrated runners."""

from __future__ import annotations

import sys

CI_CHECK_EXECUTION_IDS: dict[str, str] = {
    "execution-budget.registry": "ci:execution-budget-registry",
    "ci-impact.registry": "ci:ci-impact-registry",
    "test-impact.registry": "ci:test-impact-registry",
    "docs.style": "ci:docs-style",
    "docs.contract": "ci:docs-contract",
    "agent.config": "ci:agent-config",
    "targets.capabilities": "ci:target-capabilities",
    "ruff.check": "ci:ruff-check",
    "ruff.format": "ci:ruff-format",
    "mypy": "ci:mypy",
    "tests.pytest": "ci:pytest",
    "coverage.policy": "ci:coverage",
    "packaging.build": "ci:package-build",
    "packaging.twine": "ci:twine-check",
    "packaging.wheel-smoke": "ci:wheel-smoke",
    "smoke.init": "ci:cli-smoke",
    "smoke.lint": "ci:cli-smoke",
    "smoke.tui": "ci:tui-smoke",
    "bootstrap.python": "bootstrap:python",
    "bootstrap.clean-tree": "bootstrap:clean-tree",
    "deps.install": "ci:deps-install",
    "deps.editable": "ci:deps-editable",
}

GATE_EXECUTION_IDS: dict[str, str] = {
    "focused-module": "gate:focused-module",
    "focused-cluster": "gate:focused-cluster",
    "pre-final": "gate:pre-final",
    "full-ci": "gate:full-ci",
    "snapshot-tests": "gate:snapshot-tests",
}

SNAPSHOT_STEP_EXECUTION_IDS: dict[str, str] = {
    "pytest": "snapshot-tests:pytest",
    "git": "snapshot-tests:git",
    "archive-create": "snapshot-tests:archive-create",
    "archive-check": "snapshot-tests:archive-check",
}


def ci_check_execution_id(check_id: str) -> str:
    mapped = CI_CHECK_EXECUTION_IDS.get(check_id)
    if mapped is not None:
        return mapped
    print(f"EXECUTION_WARNING=unknown-check-id={check_id}", file=sys.stderr)
    return "ci:unknown-check"


def snapshot_step_execution_id(step_id: str) -> str:
    mapped = SNAPSHOT_STEP_EXECUTION_IDS.get(step_id)
    if mapped is not None:
        return mapped
    print(f"EXECUTION_WARNING=unknown-snapshot-step={step_id}", file=sys.stderr)
    return "snapshot-tests:unknown"
