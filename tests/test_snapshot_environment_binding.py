"""Snapshot environment binding ties archives to spell-sync environment inputs."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

from scripts.snapshot_dev_paths import resolve_spell_sync_dev_root

ROOT = Path(__file__).resolve().parents[1]


def _resolve_dev_root() -> Path | None:
    return resolve_spell_sync_dev_root(ROOT)


def _load_modules(dev_root: Path):
    scripts_dir = dev_root / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    snap_spec = importlib.util.spec_from_file_location(
        "create_code_snapshot_env_binding", scripts_dir / "create-code-snapshot.py"
    )
    policy_spec = importlib.util.spec_from_file_location(
        "snapshot_policy_env_binding", scripts_dir / "snapshot_policy.py"
    )
    assert snap_spec and snap_spec.loader and policy_spec and policy_spec.loader
    policy_mod = importlib.util.module_from_spec(policy_spec)
    snap_mod = importlib.util.module_from_spec(snap_spec)
    sys.modules[policy_spec.name] = policy_mod
    sys.modules[snap_spec.name] = snap_mod
    policy_spec.loader.exec_module(policy_mod)
    sys.modules["snapshot_policy"] = policy_mod
    snap_spec.loader.exec_module(snap_mod)
    return snap_mod, policy_mod


@pytest.fixture(scope="module")
def modules():
    dev_root = _resolve_dev_root()
    if dev_root is None or not (dev_root / "scripts" / "create-code-snapshot.py").is_file():
        pytest.skip("spell-sync-dev repository missing for snapshot environment tests")
    return _load_modules(dev_root)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _workspace_layout(snapshot_mod):
    workspace_root = ROOT.parent.parent
    return snapshot_mod.WorkspaceLayout(
        root=workspace_root,
        name="code",
        repositories={
            "spell-words": workspace_root / "spell-words",
            "spell-sync-dev": workspace_root / "spell-sync-dev",
            "spell-sync": ROOT,
        },
    )


def _required_inputs(snapshot_mod, policy_mod, layout) -> dict[str, str]:
    dev_root = _resolve_dev_root()
    assert dev_root is not None
    policy = policy_mod.load_snapshot_policy(dev_root / "snapshot-policy.toml")
    return snapshot_mod._require_environment_inputs(layout, policy)


def _environment_binding(snapshot_mod, policy_mod, layout) -> dict[str, object]:
    dev_root = _resolve_dev_root()
    assert dev_root is not None
    policy = policy_mod.load_snapshot_policy(dev_root / "snapshot-policy.toml")
    required_inputs = snapshot_mod._require_environment_inputs(layout, policy)
    inventory = policy.inventory_from_archive_entries(())
    evidence = ROOT / ".artifacts" / "environment" / "environment.json"
    evidence_sha = _sha256_file(evidence) if evidence.is_file() else ""
    return snapshot_mod._legacy_environment_fields(
        policy,
        required_inputs=required_inputs,
        evidence_sha=evidence_sha,
        inventory=inventory,
    )


def test_compute_environment_binding_matches_repository_files(modules) -> None:
    snapshot_mod, policy_mod = modules
    evidence = ROOT / ".artifacts" / "environment" / "environment.json"
    if not evidence.is_file():
        pytest.skip("maintainer environment evidence required for binding test")
    layout = _workspace_layout(snapshot_mod)
    dev_root = _resolve_dev_root()
    assert dev_root is not None
    policy = policy_mod.load_snapshot_policy(dev_root / "snapshot-policy.toml")
    required_inputs = snapshot_mod._require_environment_inputs(layout, policy)
    inventory = policy.inventory_from_archive_entries(())
    binding = snapshot_mod._compute_environment_binding(
        layout,
        policy,
        required_inputs=required_inputs,
        inventory=inventory,
    )
    expected = _environment_binding(snapshot_mod, policy_mod, layout)
    assert binding == expected


def _write_synthetic_archive(
    snapshot_mod, policy_mod, path: Path, *, environment: dict[str, object]
) -> None:
    dev_root = _resolve_dev_root()
    assert dev_root is not None
    policy = policy_mod.load_snapshot_policy(dev_root / "snapshot-policy.toml")
    prefix = "code"
    rel = policy.authoritative_project_path
    base = f"{prefix}/{rel}"
    file_entries = {
        f"{base}/pyproject.toml": ROOT / "pyproject.toml",
        f"{base}/uv.lock": ROOT / "uv.lock",
        f"{base}/.python-version": ROOT / ".python-version",
        f"{base}/config/environment-contract.toml": ROOT / "config" / "environment-contract.toml",
    }
    evidence = ROOT / ".artifacts" / "environment" / "environment.json"
    ci_summary = ROOT / ".artifacts" / "ci" / "ci-summary.json"
    if evidence.is_file():
        file_entries[f"{base}/.artifacts/environment/environment.json"] = evidence
    if ci_summary.is_file():
        file_entries[f"{base}/.artifacts/ci/ci-summary.json"] = ci_summary

    inner_paths = tuple(
        arcname[len(f"{prefix}/") :] for arcname in file_entries if arcname.startswith(f"{prefix}/")
    )
    inventory = policy.inventory_from_archive_entries(inner_paths)
    retained_artifacts = {
        artifact_path: {
            "required": artifact_path in policy.retained_artifacts_required,
            "present": artifact_path in inner_paths,
            "sha256": _sha256_file(source)
            if (source := file_entries.get(f"{prefix}/{artifact_path}")) is not None
            else None,
        }
        for artifact_path in policy.all_retained_artifact_paths()
    }
    for artifact_path in policy.retained_artifacts_required:
        entry = retained_artifacts[artifact_path]
        assert isinstance(entry.get("sha256"), str)

    manifest = {
        "schemaVersion": snapshot_mod.SCHEMA_VERSION,
        "createdAt": "2026-01-01T00:00:00+00:00",
        "workspaceName": prefix,
        "archiveName": "code.zip",
        "repositories": [
            {
                "name": "spell-words",
                "path": "spell-words",
                "head": "a",
                "branch": "main",
                "clean": True,
                "statusEntryCount": 0,
            },
            {
                "name": "spell-sync-dev",
                "path": "spell-sync-dev",
                "head": "b",
                "branch": "main",
                "clean": True,
                "statusEntryCount": 0,
            },
            {
                "name": "spell-sync",
                "path": rel,
                "head": "c",
                "branch": "main",
                "clean": True,
                "statusEntryCount": 0,
            },
        ],
        "environment": environment,
        "policy": {
            "snapshotPolicySha256": policy.digest(),
            "retainedArtifacts": retained_artifacts,
            **inventory.to_manifest_dict(),
        },
        "archive": {},
        "skippedSpecialEntries": [],
    }

    while True:
        manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{prefix}/", "")
            zf.writestr(f"{prefix}/spell-words/", "")
            zf.writestr(f"{prefix}/spell-sync-dev/", "")
            for arcname, source in file_entries.items():
                zf.writestr(arcname, source.read_bytes())
            zf.writestr(f"{prefix}/SNAPSHOT_MANIFEST.json", manifest_text)
        with zipfile.ZipFile(path, mode="r") as zf:
            stats = snapshot_mod._count_zip_entries(zf)
        archive_meta = {
            "fileCount": stats.file_count,
            "directoryCount": stats.directory_count,
            "symlinkCount": stats.symlink_count,
            "uncompressedBytes": stats.uncompressed_bytes,
            "skippedSpecialEntryCount": 0,
        }
        if manifest["archive"] == archive_meta:
            break
        manifest["archive"] = archive_meta


def test_verify_archive_rejects_tampered_environment_binding(modules, tmp_path: Path) -> None:
    snapshot_mod, policy_mod = modules
    evidence = ROOT / ".artifacts" / "environment" / "environment.json"
    ci_summary = ROOT / ".artifacts" / "ci" / "ci-summary.json"
    if not evidence.is_file() or not ci_summary.is_file():
        pytest.skip("maintainer CI/environment artifacts required for binding verify test")
    archive = tmp_path / "code.zip"
    binding = _environment_binding(snapshot_mod, policy_mod, _workspace_layout(snapshot_mod))
    _write_synthetic_archive(snapshot_mod, policy_mod, archive, environment=binding)

    layout = _workspace_layout(snapshot_mod)
    snapshot_mod.verify_archive(archive, layout=layout, states=None, stats=None, exclude_paths=None)

    tampered = tmp_path / "tampered.zip"
    shutil.copy2(archive, tampered)
    with zipfile.ZipFile(tampered, mode="r") as zf:
        manifest_name = "code/SNAPSHOT_MANIFEST.json"
        payload = json.loads(zf.read(manifest_name))
        required_inputs = payload["environment"]["requiredInputs"]
        pyproject_path = "spell-words/spell-sync/pyproject.toml"
        required_inputs[pyproject_path] = "0" * 64
        payload["environment"]["requiredInputs"] = required_inputs
        payload["environment"]["pyprojectSha256"] = "0" * 64
        entries = [
            (info, zf.read(info.filename))
            for info in zf.infolist()
            if info.filename != manifest_name
        ]
    with zipfile.ZipFile(tampered, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for info, content in entries:
            zf.writestr(info, content)
        zf.writestr(manifest_name, json.dumps(payload, indent=2, sort_keys=True) + "\n")

    with pytest.raises(snapshot_mod.SnapshotError) as exc:
        snapshot_mod.verify_archive(
            tampered, layout=layout, states=None, stats=None, exclude_paths=None
        )
    assert exc.value.failed_id == "snapshot.manifest-mismatch"
