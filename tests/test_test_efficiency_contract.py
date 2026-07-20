#!/usr/bin/env python3
"""Contract tests for test-efficiency workflow integration."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_validator(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def agent_config():
    return _load_validator("check_agent_config", ROOT / "scripts" / "check-agent-config.py")


@pytest.fixture(scope="module")
def docs_contract():
    return _load_validator("check_docs_contract", ROOT / "scripts" / "check-docs-contract.py")


def test_test_efficiency_rule_exists() -> None:
    path = ROOT / ".cursor" / "rules" / "test-efficiency.mdc"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "alwaysApply: true" in text
    assert "scripts/test_plan.py" in text


def test_select_and_run_tests_skill_exists() -> None:
    path = ROOT / ".cursor" / "skills" / "select-and-run-tests" / "SKILL.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8").lower()
    assert "this skill does not run full ci" in text


def test_agent_config_enforces_test_efficiency_contract(agent_config) -> None:
    errors = agent_config.validate_agent_config(ROOT)
    efficiency_errors = [err for err in errors if "TEST-EFFICIENCY" in err]
    assert efficiency_errors == []


def test_docs_contract_requires_testing_strategy(docs_contract) -> None:
    violations = docs_contract.check_repository(ROOT)
    test_violations = [v for v in violations if v.check_id.startswith("TEST-")]
    assert test_violations == []


def test_ci_runner_lists_diagnostic_checks() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/ci_runner.py", "--list-checks"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    ids = proc.stdout.splitlines()
    assert "ruff.format" in ids
    assert "tests.pytest" in ids


def test_modifying_skills_reference_select_and_run_tests() -> None:
    for skill in ("execute-current-phase", "apply-phase-fixes", "architecture-refactor"):
        path = ROOT / ".cursor" / "skills" / skill / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        assert "select-and-run-tests" in text


def test_spell_sync_ci_mentions_final_evidence_once() -> None:
    path = ROOT / ".cursor" / "skills" / "spell-sync-ci" / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    assert "finalEvidence" in text
    assert "select-and-run-tests" in text


def test_unrelated_docs_edit_does_not_invalidate_runtime_key() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts.test_selection.digest import compute_run_key

    key = compute_run_key(
        root=ROOT,
        command=["python3", "-m", "pytest", "tests/test_runtime_architecture.py", "-q"],
        targets=["tests/test_runtime_architecture.py"],
        clusters=["runtime"],
        tree_paths=["spell_sync/application/runtime_resolver.py"],
    )
    assert len(key) == 64


def test_safety_cluster_cannot_be_manually_excluded() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts.test_selection.planner import build_plan
    from scripts.test_selection.registry import load_registry

    registry = load_registry(ROOT / "tests" / "test-impact.toml")
    plan = build_plan(
        ROOT,
        ["spell_sync/push_prepared.py"],
        registry=registry,
    )
    assert "push" in plan.clusters
    assert "transaction" in plan.clusters


def test_full_ci_result_not_confused_with_focused_evidence() -> None:
    ci_runner = (ROOT / "scripts" / "ci_runner.py").read_text(encoding="utf-8")
    assert "finalEvidence" in ci_runner
    runner = (ROOT / "scripts" / "run_focused_tests.py").read_text(encoding="utf-8")
    assert "TEST_RUN_RESULT" in runner
    assert "CI_RESULT" not in runner
