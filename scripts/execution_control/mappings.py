"""Stable execution ID mappings for integrated runners."""

from __future__ import annotations

CI_CHECK_EXECUTION_IDS: dict[str, str] = {
    "ci-impact.registry": "ci:validators",
    "execution-budget.registry": "ci:validators",
    "test-impact.registry": "ci:validators",
    "docs.style": "ci:validators",
    "docs.contract": "ci:validators",
    "agent.config": "ci:validators",
    "targets.capabilities": "ci:validators",
    "ruff.check": "ci:ruff-check",
    "ruff.format": "ci:ruff-format",
    "mypy": "ci:mypy",
    "tests.pytest": "ci:pytest",
    "coverage.policy": "ci:coverage",
    "packaging.build": "ci:package-build",
    "packaging.twine": "ci:twine-check",
    "packaging.wheel-smoke": "ci:wheel-install",
    "smoke.init": "ci:cli-smoke",
    "smoke.lint": "ci:cli-smoke",
    "smoke.tui": "ci:tui-smoke",
}

GATE_EXECUTION_IDS: dict[str, str] = {
    "focused-module": "gate:focused-module",
    "focused-cluster": "gate:focused-cluster",
    "pre-final": "gate:pre-final",
    "full-ci": "gate:full-ci",
    "snapshot-tests": "gate:snapshot-tests",
}


def ci_check_execution_id(check_id: str) -> str:
    return CI_CHECK_EXECUTION_IDS.get(check_id, "ci:validators")
