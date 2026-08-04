#!/usr/bin/env python3
"""Contract tests for test-efficiency workflow integration."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import check_agent_config, check_docs_contract  # noqa: E402


@pytest.fixture(scope="module")
def agent_config():
    return check_agent_config


@pytest.fixture(scope="module")
def docs_contract():
    return check_docs_contract


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
    assert "tests:rest" in ids
    assert "tests:tui" in ids
    assert "tests:dev-tooling" in ids


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
    from scripts.test_selection.plan_steps import PlannedStep

    steps = (
        PlannedStep(
            kind="pytest",
            argv=("python3", "-m", "pytest", "tests/test_runtime_architecture.py", "-q"),
        ),
    )
    metadata = ("schema=2", "level=2", "clusters=runtime", "required=")
    key = compute_run_key(root=ROOT, steps=steps, metadata=metadata)
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


def test_all_registry_test_targets_exist() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/validate_test_impact.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "TEST_IMPACT_VALIDATION=success" in proc.stdout


def test_safety_critical_clusters_declare_validators() -> None:
    from scripts.test_selection.registry import SAFETY_CRITICAL_CLUSTERS, load_registry

    registry = load_registry(ROOT / "tests" / "test-impact.toml")
    for name in sorted(SAFETY_CRITICAL_CLUSTERS):
        assert registry.clusters[name].validators, f"{name} missing validators"


def test_validate_flags_empty_safety_validators(monkeypatch: pytest.MonkeyPatch) -> None:
    from dataclasses import replace

    from scripts import validate_test_impact as vit
    from scripts.test_selection.registry import load_registry

    real = load_registry(ROOT / "tests" / "test-impact.toml")
    clusters = dict(real.clusters)
    clusters["pull"] = replace(clusters["pull"], validators=())
    monkeypatch.setattr(vit, "load_registry", lambda path: replace(real, clusters=clusters))
    errors = vit.validate(ROOT)
    assert any("TEST-IMPACT-VALIDATOR-002" in err and "cluster: pull" in err for err in errors)


def test_validate_flags_unlisted_multi_importer_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    from dataclasses import replace

    from scripts import validate_test_impact as vit
    from scripts.test_selection.registry import load_registry

    real = load_registry(ROOT / "tests" / "test-impact.toml")
    remaining = tuple(path for path in real.shared_fixtures if path != "tests/tui/fake_service.py")
    assert "tests/tui/fake_service.py" in real.shared_fixtures
    monkeypatch.setattr(
        vit,
        "load_registry",
        lambda path: replace(real, shared_fixtures=remaining),
    )
    errors = vit.validate(ROOT)
    assert any(
        "TEST-IMPACT-FIXTURE-002" in err and "tests/tui/fake_service.py" in err for err in errors
    )


def test_validate_flags_module_tests_outside_cluster_tests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace

    from scripts import validate_test_impact as vit
    from scripts.test_selection.registry import load_registry

    real = load_registry(ROOT / "tests" / "test-impact.toml")
    clusters = dict(real.clusters)
    pull = clusters["pull"]
    clusters["pull"] = replace(
        pull,
        module_tests=(*pull.module_tests, "tests/test_ci_impact.py"),
    )
    monkeypatch.setattr(vit, "load_registry", lambda path: replace(real, clusters=clusters))
    errors = vit.validate(ROOT)
    assert any("TEST-IMPACT-TARGET-003" in err and "cluster: pull" in err for err in errors)


def test_group_order_matches_manifest() -> None:
    from scripts.test_groups import GROUP_ORDER, load_test_groups, validate_group_order

    ok, problems = validate_group_order()
    assert ok, problems
    assert tuple(group.group_id for group in load_test_groups()) == GROUP_ORDER


def test_empty_group_command_fails_closed() -> None:
    from scripts import test_groups as tg

    with pytest.raises(ValueError, match="test group has no files"):
        tg.pytest_command_for_group("tests:does-not-exist", "python3", root=ROOT)


def test_underscore_test_suffix_files_are_grouped() -> None:
    from scripts.test_groups import all_test_files, assign_group, load_test_groups

    groups = load_test_groups()
    relative = {path.relative_to(ROOT).as_posix() for path in all_test_files(ROOT)}
    assert "tests/arbitrary_validation_test.py" in relative
    assert assign_group("tests/arbitrary_validation_test.py", groups) == "tests:rest"


def test_shared_fixture_helpers_select_pytest_clusters() -> None:
    from scripts.test_selection.registry import (
        ALL_PYTEST_CLUSTERS,
        clusters_for_file,
        load_registry,
    )

    registry = load_registry(ROOT / "tests" / "test-impact.toml")
    for fixture in (
        "tests/journal_test_utils.py",
        "tests/conftest_execution.py",
        "tests/support/wiring.py",
        "tests/tui/fake_service.py",
        "tests/tui/test_helpers.py",
    ):
        selected = clusters_for_file(fixture, registry)
        assert selected == set(ALL_PYTEST_CLUSTERS), fixture


def test_full_ci_result_not_confused_with_focused_evidence() -> None:
    ci_runner = (ROOT / "scripts" / "ci_runner.py").read_text(encoding="utf-8")
    assert "finalEvidence" in ci_runner
    runner = (ROOT / "scripts" / "run_focused_tests.py").read_text(encoding="utf-8")
    assert "TEST_RUN_RESULT" in runner
    assert "CI_RESULT" not in runner
