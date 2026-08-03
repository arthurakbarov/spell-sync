"""Atomic snapshot output helpers from spell-sync-dev create-code-snapshot."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.execution_control.snapshot_workspace import resolve_spell_sync_dev_root

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEV_ROOT = Path("/Users/arthurakbarov/code/spell-sync-dev")


def _load_snapshot_module():
    dev_root = resolve_spell_sync_dev_root(ROOT)
    if dev_root is None and DEFAULT_DEV_ROOT.is_dir():
        dev_root = DEFAULT_DEV_ROOT
    if dev_root is None:
        pytest.skip("spell-sync-dev create-code-snapshot.py unavailable")
    script = dev_root / "scripts" / "create-code-snapshot.py"
    if not script.is_file():
        pytest.skip(f"missing snapshot script: {script}")
    module_name = "create_code_snapshot_atomic"
    spec = importlib.util.spec_from_file_location(module_name, script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_fsync_path_helper_exists_and_calls_os_fsync(tmp_path: Path) -> None:
    snapshot = _load_snapshot_module()
    target = tmp_path / "archive.zip"
    target.write_bytes(b"payload\n")
    with patch.object(os, "fsync") as fsync_mock:
        snapshot._fsync_path(target)
    fsync_mock.assert_called_once()


def test_should_skip_path_excludes_dot_venv_from_archive_walk(tmp_path: Path) -> None:
    snapshot = _load_snapshot_module()
    policy = snapshot._load_policy()
    workspace = tmp_path / "code"
    venv_entry = workspace / "spell-sync-dev" / ".venv" / "pyvenv.cfg"
    venv_entry.parent.mkdir(parents=True)
    venv_entry.write_text("home = /tmp/venv\n", encoding="utf-8")
    exclude = snapshot._archive_exclude_paths(output=tmp_path / "code.zip")
    assert snapshot._should_skip_path(
        venv_entry,
        exclude_paths=exclude,
        root=workspace,
        policy=policy,
    )


def test_create_snapshot_uses_beside_output_candidate_name() -> None:
    snapshot = _load_snapshot_module()
    dev_root = resolve_spell_sync_dev_root(ROOT) or DEFAULT_DEV_ROOT
    text = (dev_root / "scripts" / "create-code-snapshot.py").read_text(encoding="utf-8")
    assert ".code.zip.tmp-" in text
    assert "os.replace(" in text
    assert hasattr(snapshot, "_fsync_path")
