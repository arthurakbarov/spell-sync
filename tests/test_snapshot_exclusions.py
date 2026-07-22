"""Snapshot archive walk must exclude disposable environment directories."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from scripts.execution_control.workspace_paths import resolve_spell_sync_dev_root

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
    module_name = "create_code_snapshot_exclusions"
    spec = importlib.util.spec_from_file_location(module_name, script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_should_skip_path_excludes_dot_venv(tmp_path: Path) -> None:
    snapshot = _load_snapshot_module()
    workspace = tmp_path / "code"
    tool = workspace / "spell-words" / "spell-sync"
    venv_python = tool / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("stub\n", encoding="utf-8")
    exclude = snapshot._archive_exclude_paths(output=tmp_path / "code.zip")
    assert snapshot._should_skip_path(venv_python, exclude_paths=exclude, root=workspace)


def test_iter_entries_omits_dot_venv_tree(tmp_path: Path) -> None:
    snapshot = _load_snapshot_module()
    workspace = tmp_path / "code"
    tool = workspace / "spell-words" / "spell-sync"
    (tool / "src").mkdir(parents=True)
    (tool / "src" / "module.py").write_text("value = 1\n", encoding="utf-8")
    venv_file = tool / ".venv" / "lib" / "secret.txt"
    venv_file.parent.mkdir(parents=True)
    venv_file.write_text("secret\n", encoding="utf-8")
    exclude = snapshot._archive_exclude_paths(output=tmp_path / "code.zip")
    archived = {
        arcname
        for _path, arcname in snapshot._iter_entries(workspace, exclude_paths=exclude)
    }
    assert any(arcname.endswith("src/module.py") for arcname in archived)
    assert not any(".venv/" in arcname for arcname in archived)


def test_snapshot_exclude_dir_names_include_dot_venv() -> None:
    snapshot = _load_snapshot_module()
    assert ".venv" in snapshot.SNAPSHOT_EXCLUDE_DIR_NAMES
