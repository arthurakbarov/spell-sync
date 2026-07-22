"""Snapshot policy parser drives archive creation and verification."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from scripts.snapshot_dev_paths import resolve_spell_sync_dev_root

ROOT = Path(__file__).resolve().parents[1]


def _load_policy_module(dev_root: Path):
    scripts = dev_root / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location("snapshot_policy", scripts / "snapshot_policy.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_snapshot_module(dev_root: Path):
    scripts = dev_root / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location(
        "create_code_snapshot", scripts / "create-code-snapshot.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def policy_bundle():
    dev_root = resolve_spell_sync_dev_root(ROOT)
    if dev_root is None:
        pytest.skip("spell-sync-dev missing")
    policy_mod = _load_policy_module(dev_root)
    snapshot_mod = _load_snapshot_module(dev_root)
    policy = policy_mod.load_snapshot_policy(dev_root / "snapshot-policy.toml")
    return policy_mod, snapshot_mod, policy


def test_create_code_snapshot_imports_policy_parser(policy_bundle) -> None:
    _policy_mod, snapshot_mod, policy = policy_bundle
    assert hasattr(snapshot_mod, "_load_policy")
    loaded = snapshot_mod._load_policy()
    assert loaded.digest() == policy.digest()


def test_policy_digest_is_stable(policy_bundle) -> None:
    policy_mod, _, policy = policy_bundle
    again = policy_mod.load_snapshot_policy(policy_mod.default_policy_path())
    assert again.digest() == policy.digest()
