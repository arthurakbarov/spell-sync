"""Snapshot environment binding ties archives to spell-sync environment inputs."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEV_ROOT = Path("/Users/arthurakbarov/code/spell-sync-dev")


def _resolve_dev_root() -> Path:
    raw = os.environ.get("SPELL_SYNC_DEV_ROOT", "").strip()
    return Path(raw).expanduser().resolve() if raw else DEFAULT_DEV_ROOT


def _load_snapshot_module(dev_root: Path):
    script = dev_root / "scripts" / "create-code-snapshot.py"
    spec = importlib.util.spec_from_file_location("create_code_snapshot", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def snapshot_mod():
    dev_root = _resolve_dev_root()
    if not (dev_root / "scripts" / "create-code-snapshot.py").is_file():
        pytest.skip("spell-sync-dev repository missing for snapshot environment tests")
    return _load_snapshot_module(dev_root)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _environment_binding() -> dict[str, object]:
    evidence = ROOT / ".artifacts" / "environment" / "environment.json"
    return {
        "pyprojectSha256": _sha256_file(ROOT / "pyproject.toml"),
        "uvLockSha256": _sha256_file(ROOT / "uv.lock"),
        "pythonVersionFileSha256": _sha256_file(ROOT / ".python-version"),
        "environmentContractSha256": _sha256_file(ROOT / "config" / "environment-contract.toml"),
        "environmentEvidenceSha256": _sha256_file(evidence) if evidence.is_file() else "",
        "venvIncluded": False,
        "cacheEntryCount": 0,
        "timingDatabaseEntryCount": 0,
    }


def test_compute_environment_binding_matches_repository_files(snapshot_mod) -> None:
    binding = snapshot_mod._compute_environment_binding(ROOT)
    expected = _environment_binding()
    assert binding == expected


def _write_synthetic_archive(snapshot_mod, path: Path, *, environment: dict[str, object]) -> None:
    prefix = "code"
    rel = "spell-words/spell-sync"
    base = f"{prefix}/{rel}"
    file_entries = {
        f"{base}/pyproject.toml": ROOT / "pyproject.toml",
        f"{base}/uv.lock": ROOT / "uv.lock",
        f"{base}/.python-version": ROOT / ".python-version",
        f"{base}/config/environment-contract.toml": ROOT / "config" / "environment-contract.toml",
    }
    evidence = ROOT / ".artifacts" / "environment" / "environment.json"
    if evidence.is_file():
        file_entries[f"{base}/.artifacts/environment/environment.json"] = evidence

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


def test_verify_archive_rejects_tampered_environment_binding(snapshot_mod, tmp_path: Path) -> None:
    archive = tmp_path / "code.zip"
    binding = _environment_binding()
    _write_synthetic_archive(snapshot_mod, archive, environment=binding)

    layout = snapshot_mod.WorkspaceLayout(
        root=tmp_path,
        name="code",
        repositories={
            "spell-words": tmp_path / "spell-words",
            "spell-sync-dev": tmp_path / "spell-sync-dev",
            "spell-sync": tmp_path / "spell-words" / "spell-sync",
        },
    )
    snapshot_mod.verify_archive(archive, layout=layout, states=None, stats=None, exclude_paths=None)

    tampered = tmp_path / "tampered.zip"
    shutil.copy2(archive, tampered)
    with zipfile.ZipFile(tampered, mode="r") as zf:
        manifest_name = "code/SNAPSHOT_MANIFEST.json"
        payload = json.loads(zf.read(manifest_name))
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
