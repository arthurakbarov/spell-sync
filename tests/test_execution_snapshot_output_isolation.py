"""Snapshot integration must use explicit temp output, not owner archive."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

SUBPROCESS_GATE = pytest.mark.skipif(
    os.environ.get("SPELL_SNAPSHOT_GATE_TEST") != "1",
    reason="full snapshot gate subprocess runs via scripts/run_snapshot_tests.py",
)

from scripts.execution_control.workspace_paths import resolve_spell_sync_dev_root  # noqa: E402

_dev = resolve_spell_sync_dev_root(ROOT)
REAL_DEV_ROOT = _dev if _dev is not None else Path("/nonexistent")


def _init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)
    marker = path / "README.md"
    marker.write_text("snapshot fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=path, check=True)


def _build_hermetic_workspace(tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / "code"
    output = tmp_path / "snapshot" / "code.zip"
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
    return workspace, output


@SUBPROCESS_GATE
def test_snapshot_runner_accepts_explicit_output(isolated_state_dir, tmp_path):
    del isolated_state_dir
    workspace, output = _build_hermetic_workspace(tmp_path)
    env = dict(os.environ)
    env["XDG_STATE_HOME"] = str(tmp_path / "state")
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/run_snapshot_tests.py",
            "--workspace-root",
            str(workspace),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    assert "--output" in (ROOT / "scripts" / "run_snapshot_tests.py").read_text(encoding="utf-8")
    assert proc.returncode == 0
    assert output.is_file() or "SNAPSHOT_STEP=archive-create" in proc.stdout


@SUBPROCESS_GATE
def test_full_snapshot_group_leaves_owner_archive_unchanged(isolated_state_dir):
    del isolated_state_dir
    owner_archive = Path.home() / "code.zip"
    if not owner_archive.is_file():
        return
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
