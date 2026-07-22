"""Execution budget registry tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.execution_control.registry import (
    REGISTRY_REL_PATH,
    load_registry,
    profile_for_execution_id,
    registry_digest,
    validate_registry,
)

ROOT = Path(__file__).resolve().parents[1]


def test_registry_loads_required_profiles(registry):
    required = {
        "focused-module",
        "focused-cluster",
        "pre-final",
        "full-ci",
        "ci-child",
        "snapshot-tests",
        "diagnostic-pytest",
        "bounded-unknown",
    }
    assert required <= set(registry.profiles)


def test_registry_guardrails(registry):
    assert validate_registry(registry) == []


def test_profile_threshold_ordering(registry):
    for profile_id, profile in registry.profiles.items():
        assert profile.initial_expected_seconds < profile.initial_soft_seconds
        assert profile.initial_soft_seconds < profile.initial_hard_seconds
        assert profile.initial_hard_seconds <= profile.hard_cap_seconds
        assert profile.hard_cap_seconds <= registry.global_hard_cap_seconds


def test_stall_sensitive_profiles_have_bounds(registry):
    profile = registry.profiles["ci-child"]
    assert profile.progress_contract
    assert profile.stall_floor_seconds > 0
    assert profile.stall_cap_seconds >= profile.stall_floor_seconds


def test_profile_for_execution_id_mappings(registry):
    assert profile_for_execution_id(registry, "gate:full-ci").profile_id == "full-ci"
    assert profile_for_execution_id(registry, "ci:pytest").profile_id == "ci-pytest"
    assert profile_for_execution_id(registry, "ci:docs-style").profile_id == "ci-validator"
    assert profile_for_execution_id(registry, "gate:unknown").profile_id == "bounded-unknown"


def test_registry_digest_is_stable(registry):
    assert registry_digest(registry) == registry_digest(registry)
    assert len(registry_digest(registry)) == 64


def test_registry_rejects_unknown_keys(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text(
        (ROOT / REGISTRY_REL_PATH)
        .read_text(encoding="utf-8")
        .replace(
            "schemaVersion = 1",
            "schemaVersion = 1\nunknownKey = true",
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown"):
        load_registry(bad)


def test_invalid_schema_version_rejected(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text("schemaVersion = 99\n[meta]\n[profiles]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="schemaVersion"):
        load_registry(bad)


def test_parent_retries_must_be_zero(tmp_path):
    content = (ROOT / REGISTRY_REL_PATH).read_text(encoding="utf-8")
    bad = tmp_path / "bad.toml"
    bad.write_text(content.replace("parentRetries = 0", "parentRetries = 1", 1), encoding="utf-8")
    with pytest.raises(ValueError, match="parentRetries"):
        load_registry(bad)
