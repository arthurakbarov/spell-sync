"""Authoritative retained artifacts are path-scoped to spell-words/spell-sync."""

from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest

from scripts.snapshot_dev_paths import resolve_spell_sync_dev_root

ROOT = Path(__file__).resolve().parents[1]


def _load_modules(dev_root: Path):
    scripts = dev_root / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    policy_spec = importlib.util.spec_from_file_location(
        "snapshot_policy", scripts / "snapshot_policy.py"
    )
    snap_spec = importlib.util.spec_from_file_location(
        "create_code_snapshot", scripts / "create-code-snapshot.py"
    )
    assert policy_spec and policy_spec.loader and snap_spec and snap_spec.loader
    policy_mod = importlib.util.module_from_spec(policy_spec)
    snap_mod = importlib.util.module_from_spec(snap_spec)
    sys.modules[policy_spec.name] = policy_mod
    sys.modules[snap_spec.name] = snap_mod
    policy_spec.loader.exec_module(policy_mod)
    snap_spec.loader.exec_module(snap_mod)
    return policy_mod.load_snapshot_policy(dev_root / "snapshot-policy.toml"), snap_mod


@pytest.fixture(scope="module")
def policy_bundle():
    dev_root = resolve_spell_sync_dev_root(ROOT)
    if dev_root is None:
        pytest.skip("spell-sync-dev missing")
    return _load_modules(dev_root)


def test_correct_public_ci_summary_allowed(policy_bundle) -> None:
    policy, _snap = policy_bundle
    rel = "spell-words/spell-sync/.artifacts/ci/ci-summary.json"
    assert policy.is_retained_artifact(rel)
    assert policy.classify_archive_entry(rel) is None


@pytest.mark.parametrize(
    "rel",
    [
        "spell-sync-dev/.artifacts/ci/ci-summary.json",
        "spell-words/.artifacts/ci/ci-summary.json",
        "unrelated/.artifacts/environment/environment.json",
        "spell-words/spell-sync/subdir/.artifacts/ci/ci-summary.json",
    ],
)
def test_wrong_repository_retained_suffix_rejected(policy_bundle, rel: str) -> None:
    policy, _snap = policy_bundle
    assert not policy.is_retained_artifact(rel)
    assert policy.classify_archive_entry(rel) == "artifact_disallowed"


def test_verify_rejects_wrong_repository_ci_summary(policy_bundle, tmp_path: Path) -> None:
    policy, snap_mod = policy_bundle
    base = tmp_path / "base.zip"
    manifest = {
        "schemaVersion": snap_mod.SCHEMA_VERSION,
        "createdAt": "2026-01-01T00:00:00+00:00",
        "workspaceName": "code",
        "archiveName": "code.zip",
        "repositories": [],
        "environment": {
            "requiredInputs": {
                path: "a" * 64 for path in policy.required_environment_archive_paths()
            },
            "excludedEntryCount": 0,
            "disallowedArtifactEntryCount": 0,
            "environmentEvidenceSha256": "b" * 64,
        },
        "policy": {
            "snapshotPolicySha256": policy.digest(),
            "policyViolationCount": 0,
            "artifactAllowedEntryCount": 0,
            "artifactDisallowedEntryCount": 0,
            "rawCiLogEntryCount": 0,
            "testRunHistoryEntryCount": 0,
            "nestedSnapshotEntryCount": 0,
            "lockEntryCount": 0,
            "retainedArtifacts": {
                path: {"required": path in policy.retained_artifacts_required, "present": False}
                for path in policy.all_retained_artifact_paths()
            },
        },
        "archive": {
            "fileCount": 1,
            "directoryCount": 1,
            "symlinkCount": 0,
            "uncompressedBytes": 10,
            "skippedSpecialEntryCount": 0,
        },
        "skippedSpecialEntries": [],
    }
    wrong_path = "code/spell-sync-dev/.artifacts/ci/ci-summary.json"
    with zipfile.ZipFile(base, mode="w") as zf:
        zf.writestr("code/", "")
        zf.writestr(wrong_path, b"{}")
        zf.writestr("code/SNAPSHOT_MANIFEST.json", json.dumps(manifest) + "\n")
    with pytest.raises(snap_mod.SnapshotError):
        snap_mod.verify_archive(base, layout=None, states=None, stats=None, policy=policy)
