"""Tampered forbidden archive entries are rejected by policy verification."""

from __future__ import annotations

import importlib.util
import json
import shutil
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
def snapshot_mod():
    dev_root = resolve_spell_sync_dev_root(ROOT)
    if dev_root is None:
        pytest.skip("spell-sync-dev missing")
    _policy, mod = _load_modules(dev_root)
    return mod


def _inject_entry(source: Path, dest: Path, arcname: str, content: bytes) -> None:
    shutil.copy2(source, dest)
    with zipfile.ZipFile(dest, mode="r") as zf:
        entries = [(i, zf.read(i.filename)) for i in zf.infolist()]
    with zipfile.ZipFile(dest, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for info, data in entries:
            zf.writestr(info, data)
        zf.writestr(arcname, content)


@pytest.mark.parametrize(
    ("arcname", "content"),
    [
        ("code/spell-words/spell-sync/foo/__pycache__/mod.pyc", b"bad"),
        ("code/spell-words/spell-sync/.ruff_cache/item", b"bad"),
        ("code/spell-words/spell-sync/build/output.txt", b"bad"),
        ("code/spell-words/spell-sync/.artifacts/test-runs/history.json", b"{}"),
        ("code/spell-words/spell-sync/.artifacts/ci/ci.log", b"log"),
        ("code/spell-words/spell-sync/nested/code.zip", b"zip"),
        ("code/spell-words/spell-sync/.spell-sync.lock", b"lock"),
    ],
)
def test_verify_rejects_injected_forbidden_entry(
    snapshot_mod, tmp_path: Path, arcname: str, content: bytes
) -> None:
    base = tmp_path / "base.zip"
    manifest = {
        "schemaVersion": snapshot_mod.SCHEMA_VERSION,
        "createdAt": "2026-01-01T00:00:00+00:00",
        "workspaceName": "code",
        "archiveName": "code.zip",
        "repositories": [],
        "environment": {
            "excludedEntryCount": 0,
            "disallowedArtifactEntryCount": 0,
            "environmentEvidenceSha256": "a" * 64,
        },
        "policy": {
            "snapshotPolicySha256": snapshot_mod._load_policy().digest(),
            "policyViolationCount": 0,
            "artifactAllowedEntryCount": 0,
            "artifactDisallowedEntryCount": 0,
            "rawCiLogEntryCount": 0,
            "testRunHistoryEntryCount": 0,
            "nestedSnapshotEntryCount": 0,
            "lockEntryCount": 0,
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
    with zipfile.ZipFile(base, mode="w") as zf:
        zf.writestr("code/", "")
        zf.writestr("code/SNAPSHOT_MANIFEST.json", json.dumps(manifest) + "\n")
    tampered = tmp_path / "tampered.zip"
    _inject_entry(base, tampered, arcname, content)
    with pytest.raises(snapshot_mod.SnapshotError):
        snapshot_mod.verify_archive(tampered, layout=None, states=None, stats=None)
