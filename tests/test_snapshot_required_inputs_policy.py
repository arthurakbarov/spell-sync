"""Required environment inputs are enforced by snapshot policy during create/verify."""

from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest

from scripts.snapshot_dev_paths import resolve_spell_sync_dev_root

ROOT = Path(__file__).resolve().parents[1]


def _policy_inventory_manifest(
    policy, *, inner_paths: tuple[str, ...] | None = None
) -> dict[str, int]:
    if inner_paths is None:
        inner_paths = ()
    inventory = policy.inventory_from_archive_entries(inner_paths)
    return inventory.to_manifest_dict()


def _base_manifest(policy_mod, snap_mod, policy, *, inner_paths: tuple[str, ...] = ()):
    inventory = _policy_inventory_manifest(policy, inner_paths=inner_paths)
    return {
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
            "retainedArtifacts": {
                path: {
                    "required": path in policy.retained_artifacts_required,
                    "present": path in inner_paths,
                }
                for path in policy.all_retained_artifact_paths()
            },
            **inventory,
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


def _retained_artifact_payloads(snap_mod) -> dict[str, bytes]:
    return {
        "spell-words/spell-sync/.artifacts/ci/ci-summary.json": b"{}",
        "spell-words/spell-sync/.artifacts/environment/environment.json": b'{"environmentCheckExit":0}',
    }


def _sync_policy_inventory(
    policy,
    manifest: dict[str, object],
    *,
    inner_paths: set[str],
) -> None:
    policy_meta = manifest["policy"]
    assert isinstance(policy_meta, dict)
    policy_meta.update(_policy_inventory_manifest(policy, inner_paths=tuple(sorted(inner_paths))))


def _apply_retained_artifacts(
    policy,
    snap_mod,
    manifest: dict[str, object],
    *,
    inner_paths: set[str],
) -> None:
    payloads = _retained_artifact_payloads(snap_mod)
    policy_meta = manifest["policy"]
    assert isinstance(policy_meta, dict)
    retained_meta = policy_meta["retainedArtifacts"]
    assert isinstance(retained_meta, dict)
    for path in policy.retained_artifacts_required:
        inner_paths.add(path)
        digest = snap_mod._sha256_bytes(payloads[path])
        retained_meta[path] = {
            "required": True,
            "present": True,
            "sha256": digest,
        }


def _write_archive(
    archive: Path,
    manifest: dict[str, object],
    *,
    file_payloads: dict[str, bytes],
) -> None:
    with zipfile.ZipFile(archive, mode="w") as zf:
        zf.writestr("code/", "")
        for path, payload in sorted(file_payloads.items()):
            zf.writestr(f"code/{path}", payload)
        zf.writestr("code/SNAPSHOT_MANIFEST.json", json.dumps(manifest) + "\n")


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
    return policy_mod, snap_mod


@pytest.fixture(scope="module")
def modules():
    dev_root = resolve_spell_sync_dev_root(ROOT)
    if dev_root is None:
        pytest.skip("spell-sync-dev missing")
    return _load_modules(dev_root)


def test_required_environment_archive_paths(modules) -> None:
    policy_mod, _snap = modules
    dev_root = resolve_spell_sync_dev_root(ROOT)
    assert dev_root is not None
    policy = policy_mod.load_snapshot_policy(dev_root / "snapshot-policy.toml")
    paths = policy.required_environment_archive_paths()
    assert "spell-words/spell-sync/pyproject.toml" in paths
    assert "spell-words/spell-sync/config/environment-contract.toml" in paths


def test_missing_required_input_rejected_on_verify(modules, tmp_path: Path) -> None:
    policy_mod, snap_mod = modules
    dev_root = resolve_spell_sync_dev_root(ROOT)
    assert dev_root is not None
    policy = policy_mod.load_snapshot_policy(dev_root / "snapshot-policy.toml")
    inner_paths: set[str] = set()
    manifest = _base_manifest(policy_mod, snap_mod, policy, inner_paths=tuple(inner_paths))
    _apply_retained_artifacts(policy, snap_mod, manifest, inner_paths=inner_paths)
    _sync_policy_inventory(policy, manifest, inner_paths=inner_paths)
    archive = tmp_path / "missing-input.zip"
    _write_archive(archive, manifest, file_payloads=_retained_artifact_payloads(snap_mod))
    with pytest.raises(snap_mod.SnapshotError) as exc:
        snap_mod.verify_archive(archive, layout=None, states=None, stats=None, policy=policy)
    assert exc.value.failed_id == "snapshot.required-input-missing"


def test_new_missing_required_input_rejected(modules, tmp_path: Path) -> None:
    policy_mod, snap_mod = modules
    dev_root = resolve_spell_sync_dev_root(ROOT)
    assert dev_root is not None
    patched_policy = tmp_path / "snapshot-policy.toml"
    patched_policy.write_text(
        """
schemaVersion = 2

[workspace]
authoritativeProjectPath = "spell-words/spell-sync"

[exclusions]
patterns = [".venv/"]

[retainedArtifacts]
required = [
  "spell-words/spell-sync/.artifacts/ci/ci-summary.json",
  "spell-words/spell-sync/.artifacts/environment/environment.json",
]
optional = []

[requiredEnvironmentInputs]
patterns = [
  "pyproject.toml",
  "uv.lock",
  ".python-version",
  "config/environment-contract.toml",
  "config/NEW_REQUIRED_FILE.toml",
]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    policy = policy_mod.load_snapshot_policy(patched_policy)
    layout = snap_mod.WorkspaceLayout(
        root=tmp_path / "workspace",
        name="code",
        repositories={
            "spell-sync": tmp_path / "workspace" / "spell-words" / "spell-sync",
            "spell-words": tmp_path / "workspace" / "spell-words",
            "spell-sync-dev": tmp_path / "workspace" / "spell-sync-dev",
        },
    )
    tool = layout.repositories["spell-sync"]
    tool.mkdir(parents=True)
    for rel in ("pyproject.toml", "uv.lock", ".python-version"):
        (tool / rel).write_text("stub\n", encoding="utf-8")
    (tool / "config").mkdir()
    (tool / "config" / "environment-contract.toml").write_text("ok\n", encoding="utf-8")
    evidence = tool / ".artifacts" / "environment" / "environment.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_text(
        json.dumps(
            {
                "environmentCheckExit": 0,
                "lockCheckExit": 0,
                "environmentFingerprint": "fp",
            }
        ),
        encoding="utf-8",
    )
    ci = tool / ".artifacts" / "ci" / "ci-summary.json"
    ci.parent.mkdir(parents=True)
    ci.write_text("{}", encoding="utf-8")
    with pytest.raises(snap_mod.SnapshotError) as exc:
        snap_mod._require_environment_inputs(layout, policy)
    assert exc.value.failed_id == "snapshot.required-input-missing"


def test_required_input_digest_mismatch_rejected(modules, tmp_path: Path) -> None:
    policy_mod, snap_mod = modules
    dev_root = resolve_spell_sync_dev_root(ROOT)
    assert dev_root is not None
    policy = policy_mod.load_snapshot_policy(dev_root / "snapshot-policy.toml")
    pyproject_path = "spell-words/spell-sync/pyproject.toml"
    inner_paths: set[str] = set(policy.required_environment_archive_paths())
    manifest = _base_manifest(policy_mod, snap_mod, policy, inner_paths=tuple(inner_paths))
    _apply_retained_artifacts(policy, snap_mod, manifest, inner_paths=inner_paths)
    _sync_policy_inventory(policy, manifest, inner_paths=inner_paths)
    required_inputs = {}
    file_payloads = dict(_retained_artifact_payloads(snap_mod))
    for path in policy.required_environment_archive_paths():
        content = b"actual-content" if path == pyproject_path else b"stable-content"
        file_payloads[path] = content
        required_inputs[path] = snap_mod._sha256_bytes(content)
    required_inputs[pyproject_path] = "d" * 64
    manifest["environment"]["requiredInputs"] = required_inputs
    archive = tmp_path / "digest-mismatch.zip"
    _write_archive(archive, manifest, file_payloads=file_payloads)
    with pytest.raises(snap_mod.SnapshotError) as exc:
        snap_mod.verify_archive(archive, layout=None, states=None, stats=None, policy=policy)
    assert exc.value.failed_id == "snapshot.manifest-mismatch"
