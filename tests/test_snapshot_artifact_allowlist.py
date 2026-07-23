"""Retained .artifacts allowlist excludes historical CI logs and test-run history."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from scripts.snapshot_dev_paths import resolve_spell_sync_dev_root

ROOT = Path(__file__).resolve().parents[1]


def _load_policy(dev_root: Path):
    scripts = dev_root / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location("snapshot_policy", scripts / "snapshot_policy.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.load_snapshot_policy(dev_root / "snapshot-policy.toml")


@pytest.fixture(scope="module")
def policy():
    dev_root = resolve_spell_sync_dev_root(ROOT)
    if dev_root is None:
        pytest.skip("spell-sync-dev missing")
    return _load_policy(dev_root)


def test_retained_ci_summary_allowed(policy) -> None:
    rel = "spell-words/spell-sync/.artifacts/ci/ci-summary.json"
    assert not policy.should_skip_workspace_path(rel)


def test_ci_log_excluded(policy) -> None:
    rel = "spell-words/spell-sync/.artifacts/ci/ci.log"
    assert policy.should_skip_workspace_path(rel)


def test_test_run_history_excluded(policy) -> None:
    rel = "spell-words/spell-sync/.artifacts/test-runs/run-1/history.json"
    assert policy.should_skip_workspace_path(rel)


def test_environment_evidence_allowed(policy) -> None:
    rel = "spell-words/spell-sync/.artifacts/environment/environment.json"
    assert not policy.should_skip_workspace_path(rel)


@pytest.mark.parametrize(
    "rel",
    [
        "spell-sync-dev/.artifacts/ci/ci-summary.json",
        "spell-words/.artifacts/environment/environment.json",
    ],
)
def test_wrong_repository_retained_artifact_skipped(policy, rel: str) -> None:
    assert policy.should_skip_workspace_path(rel)
    assert policy.classify_archive_entry(rel) == "artifact_disallowed"
