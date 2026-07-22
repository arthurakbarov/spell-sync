"""Hermetic snapshot gate tests without owner HOME dependencies."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

from scripts.execution_control.workspace_paths import resolve_spell_sync_dev_root  # noqa: E402

_dev = resolve_spell_sync_dev_root(ROOT)
REAL_DEV_ROOT = _dev if _dev is not None else Path("/nonexistent")

SUBPROCESS_GATE = pytest.mark.skipif(
    os.environ.get("SPELL_SNAPSHOT_GATE_TEST") != "1",
    reason="full snapshot gate subprocess runs via scripts/run_snapshot_tests.py",
)


def _init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)
    marker = path / "README.md"
    marker.write_text("snapshot fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=path, check=True)


def _build_hermetic_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "code"
    words = workspace / "spell-words"
    tool = words / "spell-sync"
    dev = workspace / "spell-sync-dev"
    _init_git_repo(words)
    if tool.exists():
        shutil.rmtree(tool)
    shutil.copytree(
        ROOT,
        tool,
        ignore=shutil.ignore_patterns(".git", ".artifacts", "__pycache__", ".venv"),
        ignore_dangling_symlinks=True,
    )
    _init_git_repo(tool)
    if REAL_DEV_ROOT.is_dir():
        if dev.exists():
            shutil.rmtree(dev)
        shutil.copytree(
            REAL_DEV_ROOT,
            dev,
            ignore=shutil.ignore_patterns(".git", ".artifacts", "__pycache__"),
        )
        _init_git_repo(dev)
    else:
        dev.mkdir(parents=True)
        scripts = dev / "scripts"
        scripts.mkdir()
        (scripts / "create-code-snapshot.py").write_text("# stub\n", encoding="utf-8")
        (dev / "tests").mkdir()
        (dev / "tests" / "test_create_code_snapshot.py").write_text(
            "def test_stub():\n    assert True\n",
            encoding="utf-8",
        )
        _init_git_repo(dev)
    return workspace


def test_snapshot_gate_requires_explicit_workspace_layout(isolated_state_dir, tmp_path):
    del isolated_state_dir
    env = dict(os.environ)
    env["XDG_STATE_HOME"] = str(tmp_path / "state")
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/run_snapshot_tests.py",
            "--workspace-root",
            str(tmp_path / "missing"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    output = proc.stdout + proc.stderr
    assert "SNAPSHOT_GATE_RESULT=blocked" in output
    assert "SNAPSHOT_GATE_FAILED_ID=snapshot.workspace-layout-invalid" in output
    assert proc.returncode != 0


@SUBPROCESS_GATE
def test_snapshot_gate_runs_in_non_home_workspace(isolated_state_dir, tmp_path):
    del isolated_state_dir
    workspace = _build_hermetic_workspace(tmp_path)
    env = dict(os.environ)
    env["XDG_STATE_HOME"] = str(tmp_path / "state")
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/run_snapshot_tests.py",
            "--workspace-root",
            str(workspace),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    output = proc.stdout + proc.stderr
    assert "EXECUTION_GATE=gate:snapshot-tests" in output
    assert proc.returncode == 0


@SUBPROCESS_GATE
def test_ordinary_pytest_does_not_mutate_owner_code_zip(isolated_state_dir):
    del isolated_state_dir
    owner_archive = Path.home() / "code.zip"
    if not owner_archive.is_file():
        pytest.skip("owner archive not present")
    before = hashlib.sha256(owner_archive.read_bytes()).hexdigest()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_execution_snapshot_hermetic.py",
            "tests/test_execution_snapshot_output_isolation.py",
            "-q",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    after = hashlib.sha256(owner_archive.read_bytes()).hexdigest()
    assert before == after
