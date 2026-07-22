#!/usr/bin/env python3
"""Tests for scripts/test_plan.py and test selection planner."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def planner_mod():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    return _load_module(
        "test_selection_planner", ROOT / "scripts" / "test_selection" / "planner.py"
    )


@pytest.fixture(scope="module")
def registry_mod():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    return _load_module(
        "test_selection_registry", ROOT / "scripts" / "test_selection" / "registry.py"
    )


@pytest.fixture(scope="module")
def registry(registry_mod):
    return registry_mod.load_registry(ROOT / "tests" / "test-impact.toml")


def test_docs_only_selects_documentation_cluster(planner_mod, registry) -> None:
    plan = planner_mod.build_plan(
        ROOT,
        ["docs/ARCHITECTURE.md"],
        registry=registry,
    )
    assert plan.clusters == ("documentation",)
    assert plan.pytest_targets == ()


def test_runtime_file_selects_runtime_cluster(planner_mod, registry) -> None:
    plan = planner_mod.build_plan(
        ROOT,
        ["spell_sync/application/runtime_resolver.py"],
        registry=registry,
    )
    assert "runtime" in plan.clusters
    assert "tests/test_runtime_architecture.py" in plan.pytest_targets


def test_push_writer_selects_push_and_transaction(planner_mod, registry) -> None:
    plan = planner_mod.build_plan(
        ROOT,
        ["spell_sync/push_prepared.py"],
        registry=registry,
    )
    assert "push" in plan.clusters
    assert "transaction" in plan.clusters
    assert "tests/test_transaction_safety.py" in plan.pytest_targets


def test_recovery_file_selects_recovery_cluster(planner_mod, registry) -> None:
    plan = planner_mod.build_plan(
        ROOT,
        ["spell_sync/recover_cmd.py"],
        registry=registry,
    )
    assert "recovery" in plan.clusters


def test_tui_file_selects_tui_cluster(planner_mod, registry) -> None:
    plan = planner_mod.build_plan(
        ROOT,
        ["spell_sync/tui/controller.py"],
        registry=registry,
    )
    assert "tui" in plan.clusters


def test_cursor_file_selects_agent_workflow(planner_mod, registry) -> None:
    plan = planner_mod.build_plan(
        ROOT,
        [".cursor/rules/test-efficiency.mdc"],
        registry=registry,
    )
    assert "agent-workflow" in plan.clusters


def test_ci_runner_selects_agent_and_ci_tests(planner_mod, registry) -> None:
    plan = planner_mod.build_plan(
        ROOT,
        ["scripts/ci_runner.py"],
        registry=registry,
    )
    assert "agent-workflow" in plan.clusters
    assert "tests/test_ci_contract.py" in plan.pytest_targets


def test_pyproject_static_targets_include_spell_sync(planner_mod, registry) -> None:
    plan = planner_mod.build_plan(ROOT, ["pyproject.toml"], registry=registry)
    assert "spell_sync" in plan.static_targets


def test_changed_python_file_static_target_is_file_path(planner_mod, registry) -> None:
    plan = planner_mod.build_plan(
        ROOT,
        ["spell_sync/runtime_settings.py"],
        registry=registry,
    )
    assert "spell_sync/runtime_settings.py" in plan.static_targets


def test_unknown_static_targets_key_rejected(registry_mod, tmp_path: Path) -> None:
    bad = tmp_path / "test-impact.toml"
    bad.write_text(
        """
[meta]
sharedFixtures = []

[fallback]
tests = []

[clusters.packaging]
production = ["pyproject.toml"]
static_targets = ["spell_sync"]
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="TEST-IMPACT-SCHEMA-002"):
        registry_mod.load_registry(bad)


def test_changed_test_file_selects_itself(planner_mod, registry) -> None:
    plan = planner_mod.build_plan(
        ROOT,
        ["tests/test_settings.py"],
        registry=registry,
    )
    assert plan.pytest_targets == ("tests/test_settings.py",)


def test_conftest_selects_all_pytest_clusters(registry_mod, registry) -> None:
    clusters = registry_mod.clusters_for_file("tests/conftest.py", registry)
    assert clusters == registry_mod.ALL_PYTEST_CLUSTERS


def test_duplicate_tests_deduplicated(planner_mod, registry) -> None:
    plan = planner_mod.build_plan(
        ROOT,
        [
            "spell_sync/push_prepared.py",
            "spell_sync/push_transaction.py",
        ],
        registry=registry,
    )
    assert len(plan.pytest_targets) == len(set(plan.pytest_targets))


def test_stable_ordering(planner_mod, registry) -> None:
    plan = planner_mod.build_plan(
        ROOT,
        ["spell_sync/push_prepared.py"],
        registry=registry,
    )
    assert list(plan.pytest_targets) == sorted(plan.pytest_targets)
    assert list(plan.clusters) == sorted(plan.clusters)


def test_unknown_production_file_conservative_fallback(planner_mod, registry) -> None:
    plan = planner_mod.build_plan(
        ROOT,
        ["spell_sync/unknown_new_module.py"],
        registry=registry,
    )
    assert "packaging" in plan.clusters
    assert any("conservative" in reason or "packaging" in reason for reason in plan.reasons)


def test_execution_control_maps_to_execution_cluster(planner_mod, registry) -> None:
    plan = planner_mod.build_plan(
        ROOT,
        ["scripts/execution_control/controller.py"],
        registry=registry,
    )
    assert plan.clusters == ("execution-control",)
    assert "tests/test_execution_controller.py" in plan.pytest_targets


def test_cluster_override(planner_mod, registry) -> None:
    plan = planner_mod.build_plan(
        ROOT,
        [],
        registry=registry,
        cluster_override="runtime",
    )
    assert plan.clusters == ("runtime",)


def test_target_override(planner_mod, registry) -> None:
    plan = planner_mod.build_plan(
        ROOT,
        [],
        registry=registry,
        target_override="tests/test_core.py",
    )
    assert plan.pytest_targets == ("tests/test_core.py",)


def test_push_runtime_override_retains_safety_clusters(planner_mod, registry) -> None:
    plan = planner_mod.build_plan(
        ROOT,
        ["spell_sync/push_prepared.py"],
        registry=registry,
        cluster_override="runtime",
    )
    assert "runtime" in plan.clusters
    assert "push" in plan.clusters
    assert "transaction" in plan.clusters


def test_target_override_is_level_zero(planner_mod, registry) -> None:
    plan = planner_mod.build_plan(
        ROOT,
        ["spell_sync/push_prepared.py"],
        registry=registry,
        target_override="tests/test_core.py",
    )
    assert plan.validation_level == 0
    assert plan.final_focused_evidence is False
    assert plan.pytest_targets == ("tests/test_core.py",)


def test_module_level_uses_module_tests(planner_mod, registry) -> None:
    plan = planner_mod.build_plan(
        ROOT,
        ["spell_sync/application/runtime_resolver.py"],
        registry=registry,
        level="module",
    )
    assert "tests/test_explicit_runtime.py" in plan.pytest_targets
    assert "tests/test_runtime_architecture.py" not in plan.pytest_targets


def test_cluster_level_uses_cluster_tests(planner_mod, registry) -> None:
    plan = planner_mod.build_plan(
        ROOT,
        ["spell_sync/application/runtime_resolver.py"],
        registry=registry,
        level="cluster",
    )
    assert "tests/test_runtime_architecture.py" in plan.pytest_targets


def test_module_tests_subset_of_cluster_tests(planner_mod, registry) -> None:
    cases = [
        "spell_sync/push_prepared.py",
        "spell_sync/settings.py",
        "spell_sync/tui/controller.py",
        "spell_sync/cli.py",
    ]
    for file_path in cases:
        module_plan = planner_mod.build_plan(
            ROOT,
            [file_path],
            registry=registry,
            level="module",
        )
        cluster_plan = planner_mod.build_plan(
            ROOT,
            [file_path],
            registry=registry,
            level="cluster",
        )
        assert set(module_plan.pytest_targets) <= set(cluster_plan.pytest_targets), file_path


def test_plan_cli_json_output() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/test_plan.py", "--files", "docs/FOO.md", "--format", "json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["schemaVersion"] == 2
    assert payload["validationLevel"] == 2
    assert payload["clusters"] == ["documentation"]


def test_no_duplicate_command_targets(planner_mod, registry) -> None:
    plan = planner_mod.build_plan(
        ROOT,
        ["spell_sync/push_prepared.py", "spell_sync/push_transaction.py"],
        registry=registry,
    )
    command_targets = [part for part in plan.command if part.startswith("tests/")]
    assert len(command_targets) == len(set(command_targets))
