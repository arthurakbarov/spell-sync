"""Stable execution ID mappings for integrated runners."""

from __future__ import annotations

import sys

CI_CHECK_EXECUTION_IDS: dict[str, str] = {
    "execution-budget.registry": "ci:execution-budget-registry",
    "dev-commands.registry": "ci:dev-commands-registry",
    "timing.observability": "ci:timing-observability",
    "ci-impact.registry": "ci:ci-impact-registry",
    "test-impact.registry": "ci:test-impact-registry",
    "docs.style": "ci:docs-style",
    "docs.contract": "ci:docs-contract",
    "architecture.boundaries": "ci:architecture",
    "agent.config": "ci:agent-config",
    "privacy.tree": "ci:privacy-tree",
    "targets.capabilities": "ci:target-capabilities",
    "ruff.check": "ci:ruff-check",
    "ruff.format": "ci:ruff-format",
    "mypy": "ci:mypy",
    "tests:rest": "tests:rest",
    "tests:tui": "tests:tui",
    "tests:dev-tooling": "tests:dev-tooling",
    "tests:environment": "tests:environment",
    "tests:packaging": "tests:packaging",
    "tests:integration": "tests:integration",
    "tests.pytest": "ci:pytest",
    "coverage.policy": "ci:coverage",
    "packaging.build": "ci:package-build",
    "packaging.twine": "ci:twine-check",
    "packaging.members": "ci:package-members",
    "packaging.wheel-smoke": "ci:wheel-smoke",
    "packaging.wheel-smoke.venv": "ci:wheel-smoke-venv",
    "packaging.wheel-smoke.install": "ci:wheel-smoke-install",
    "packaging.wheel-smoke.origin": "ci:wheel-smoke-origin",
    "packaging.wheel-smoke.version": "ci:wheel-smoke-version",
    "packaging.wheel-smoke.cli-version": "ci:wheel-smoke-cli-version",
    "packaging.wheel-smoke.cli-help": "ci:wheel-smoke-cli-help",
    "packaging.wheel-smoke.support-report": "ci:wheel-smoke-support-report",
    "smoke.init": "ci:cli-smoke",
    "smoke.lint": "ci:cli-smoke",
    "smoke.tui": "ci:tui-smoke",
    "bootstrap.python": "bootstrap:python",
    "bootstrap.clean-tree": "bootstrap:clean-tree",
    "environment.contract": "ci:environment-contract",
    "environment.lock": "ci:environment-lock",
    "environment.check": "ci:environment-check",
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
