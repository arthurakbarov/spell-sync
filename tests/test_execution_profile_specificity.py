"""Execution profile specificity tests."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.registry import (  # noqa: E402
    REGISTRY_REL_PATH,
    load_registry,
    profile_for_execution_id,
)


def test_ci_pytest_uses_dedicated_profile(registry):
    profile = profile_for_execution_id(registry, "ci:pytest")
    assert profile.profile_id == "ci-pytest"
    assert profile.execution_id == "ci:pytest"
    assert profile.initial_hard_seconds == 420


def test_ci_docs_style_uses_validator_profile(registry):
    profile = profile_for_execution_id(registry, "ci:docs-style")
    assert profile.profile_id == "ci-validator"
    assert profile.initial_hard_seconds == 120


def test_pytest_profile_does_not_change_docs_validator_hard(registry):
    pytest_profile = profile_for_execution_id(registry, "ci:pytest")
    docs_profile = profile_for_execution_id(registry, "ci:docs-style")
    assert pytest_profile.initial_hard_seconds > docs_profile.initial_hard_seconds
    assert docs_profile.initial_hard_seconds <= 120


def test_unknown_child_does_not_inherit_pytest_budget(registry):
    profile = profile_for_execution_id(registry, "ci:unknown-check")
    assert profile.profile_id == "bounded-unknown"
    assert (
        profile.initial_hard_seconds
        != profile_for_execution_id(registry, "ci:pytest").initial_hard_seconds
    )


def test_ci_child_generic_profile_restored(registry):
    profile = profile_for_execution_id(registry, "ci:ruff-check")
    assert profile.profile_id == "ci-child"
    assert profile.initial_hard_seconds == 300


def test_focused_planner_has_dedicated_profile(registry):
    profile = profile_for_execution_id(registry, "focused:planner")
    assert profile.profile_id == "focused-planner"


def test_pytest_profile_documents_measured_evidence(registry):
    profile = profile_for_execution_id(registry, "ci:pytest")
    assert "measured" in profile.source or "pytest" in profile.source


def test_registry_loads_from_committed_path():
    registry = load_registry(ROOT / REGISTRY_REL_PATH)
    assert "ci-pytest" in registry.profiles
    assert registry.child_mappings["ci:pytest"].profile_id == "ci-pytest"
