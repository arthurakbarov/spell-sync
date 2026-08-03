"""Integration tests for execution control boundaries."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.execution_control.controller import ExecutionController
from scripts.execution_control.history import HistoryStore
from scripts.execution_control.mappings import (
    CI_CHECK_EXECUTION_IDS,
    GATE_EXECUTION_IDS,
    ci_check_execution_id,
)
from scripts.execution_control.models import ExecutionStatus
from scripts.execution_control.registry import profile_for_execution_id
from scripts.execution_control.state_paths import history_database_path, state_root

ROOT = Path(__file__).resolve().parents[1]


def _fake_necessity(result: str = "full-required"):
    return SimpleNamespace(
        assess_ci_necessity=lambda _root: SimpleNamespace(
            result=result,
            reusable_run_head="",
        )
    )


def test_state_directory_outside_repository(isolated_state_dir):
    del isolated_state_dir
    repo = ROOT.resolve()
    assert not str(state_root().resolve()).startswith(str(repo))
    assert not str(history_database_path().resolve()).startswith(str(repo))


def test_duplicate_active_execution_blocked(isolated_state_dir, registry):
    del isolated_state_dir
    history = HistoryStore.open()
    controller = ExecutionController(root=ROOT, registry=registry, history=history)
    with patch(
        "scripts.execution_control.admission._load_ci_necessity",
        return_value=_fake_necessity(),
    ):
        first, state1 = controller.prepare_plan(
            execution_id="gate:focused-module",
            command=["python3", "-m", "pytest"],
            mode="exact",
            required=True,
        )
        second, state2 = controller.prepare_plan(
            execution_id="gate:focused-module",
            command=["python3", "-m", "pytest"],
            mode="exact",
            required=True,
        )
    assert first is not None and state1 == "run"
    assert second is None and state2 == ExecutionStatus.BLOCKED_DUPLICATE.value


def test_stale_lease_allows_new_execution(isolated_state_dir, history):
    del isolated_state_dir
    signature = "integration-stale-lease" * 2
    acquired, _ = history.acquire_lease(
        normalized_signature=signature,
        run_id="stale-run",
        execution_id="gate:focused-module",
        owner_pid=999999,
    )
    assert acquired is True
    reacquired, owner = history.acquire_lease(
        normalized_signature=signature,
        run_id="fresh-run",
        execution_id="gate:focused-module",
        owner_pid=os.getpid(),
    )
    assert reacquired is True
    assert owner is None


def test_ci_check_execution_id_mappings():
    assert ci_check_execution_id("ruff.check") == "ci:ruff-check"
    assert ci_check_execution_id("tests:rest") == "tests:rest"
    assert ci_check_execution_id("tests:tui") == "tests:tui"
    assert ci_check_execution_id("execution-budget.registry") == "ci:execution-budget-registry"
    assert ci_check_execution_id("unknown-check") == "ci:unknown-check"
    assert "mypy" in CI_CHECK_EXECUTION_IDS
    assert GATE_EXECUTION_IDS["full-ci"] == "gate:full-ci"


def test_ci_child_mappings_resolve_profile(registry):
    profile = profile_for_execution_id(registry, "ci:mypy")
    assert profile.profile_id == "ci-child"
    parent_mapping = registry.child_mappings["ci:mypy"]
    assert parent_mapping.parent_execution_id == "gate:full-ci"


def test_product_paths_not_wrapped_by_controller():
    candidates = (
        "spell_sync/application/services/pull.py",
        "spell_sync/application/services/push.py",
        "spell_sync/application/services/recovery.py",
        "spell_sync/application/service.py",
        "spell_sync/application/services/sync.py",
        "spell_sync/sync_run.py",
    )
    checked = 0
    for rel in candidates:
        path = ROOT / rel
        if not path.is_file():
            continue
        checked += 1
        text = path.read_text(encoding="utf-8")
        assert "execution_control" not in text
        assert "run_monitored_command" not in text
    assert checked >= 1


def test_snapshot_tests_profile_exists_and_mapped(registry):
    assert "snapshot-tests" in registry.profiles
    profile = registry.profiles["snapshot-tests"]
    assert profile.execution_id == "gate:snapshot-tests"
    assert "snapshot-tests:pytest" in registry.child_mappings
    snapshot_child = registry.child_mappings["snapshot-tests:pytest"]
    assert snapshot_child.parent_execution_id == "gate:snapshot-tests"


def test_artifacts_gitignored():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".artifacts/" in gitignore


def test_reuse_does_not_create_duration_sample(registry, history, isolated_state_dir):
    del isolated_state_dir
    from scripts.execution_control.admission import assess_admission

    profile = profile_for_execution_id(registry, "gate:focused-cluster")
    fake = SimpleNamespace(
        assess_ci_necessity=lambda _root: SimpleNamespace(
            result="no-action",
            reusable_run_head="head",
        )
    )
    with patch("scripts.execution_control.admission._load_ci_necessity", return_value=fake):
        admission, plan = assess_admission(
            ROOT,
            execution_id="gate:focused-cluster",
            profile=profile,
            registry=registry,
            history=history,
            command=["python", "-m", "pytest"],
            mode="cluster",
            required=False,
        )
    assert plan is None
    assert history.fetch_profile_durations(execution_id="gate:focused-cluster") == []
