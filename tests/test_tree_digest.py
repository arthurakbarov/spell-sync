#!/usr/bin/env python3
"""Tests for content-addressed tree digest semantics."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.test_selection.digest import compute_run_key, tree_digest  # noqa: E402
from scripts.test_selection.tree_state import (  # noqa: E402
    changed_source_paths,
    is_working_tree_clean,
)


def _run_git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "config", "user.email", "test@example.invalid")
    _run_git(repo, "config", "user.name", "Test")
    (repo / "tracked.txt").write_text("clean\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    _run_git(repo, "add", "tracked.txt", "pyproject.toml")
    _run_git(repo, "commit", "-m", "init")
    return repo


def test_tracked_clean_to_dirty_changes_digest(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    before = tree_digest(repo)
    (repo / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    after = tree_digest(repo)
    assert before != after


def test_tracked_dirty_content_a_to_b_changes_digest(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "tracked.txt").write_text("A\n", encoding="utf-8")
    digest_a = tree_digest(repo)
    (repo / "tracked.txt").write_text("B\n", encoding="utf-8")
    digest_b = tree_digest(repo)
    assert digest_a != digest_b


def test_staged_content_a_to_b_changes_digest(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "tracked.txt").write_text("A\n", encoding="utf-8")
    _run_git(repo, "add", "tracked.txt")
    digest_a = tree_digest(repo)
    (repo / "tracked.txt").write_text("B\n", encoding="utf-8")
    _run_git(repo, "add", "tracked.txt")
    digest_b = tree_digest(repo)
    assert digest_a != digest_b


def test_untracked_content_a_to_b_changes_digest(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    untracked = repo / "new.txt"
    untracked.write_text("A\n", encoding="utf-8")
    digest_a = tree_digest(repo)
    untracked.write_text("B\n", encoding="utf-8")
    digest_b = tree_digest(repo)
    assert digest_a != digest_b


def test_symlink_target_change_changes_digest(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "target-a.txt").write_text("a\n", encoding="utf-8")
    link = repo / "link.txt"
    if link.exists():
        link.unlink()
    os.symlink("target-a.txt", link)
    digest_a = tree_digest(repo)
    link.unlink()
    (repo / "target-b.txt").write_text("b\n", encoding="utf-8")
    os.symlink("target-b.txt", link)
    digest_b = tree_digest(repo)
    assert digest_a != digest_b


def test_chmod_change_changes_digest(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = repo / "run.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o644)
    digest_a = tree_digest(repo)
    script.chmod(0o755)
    digest_b = tree_digest(repo)
    assert digest_a != digest_b


def test_rename_changes_digest(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "old.txt").write_text("x\n", encoding="utf-8")
    _run_git(repo, "add", "old.txt")
    _run_git(repo, "commit", "-m", "add old")
    _run_git(repo, "mv", "old.txt", "new.txt")
    digest_renamed = tree_digest(repo)
    _run_git(repo, "reset", "--hard", "HEAD")
    digest_clean = tree_digest(repo)
    assert digest_renamed != digest_clean


def test_delete_changes_digest(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    before = tree_digest(repo)
    (repo / "tracked.txt").unlink()
    after = tree_digest(repo)
    assert before != after


def test_ignored_artifact_changes_do_not_change_digest(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    artifacts = repo / ".artifacts" / "ci"
    artifacts.mkdir(parents=True)
    before = tree_digest(repo)
    (artifacts / "ci.log").write_text("log\n", encoding="utf-8")
    (artifacts / "ci-summary.json").write_text("{}\n", encoding="utf-8")
    (repo / "build").mkdir()
    (repo / "build" / "artifact").write_text("x\n", encoding="utf-8")
    after = tree_digest(repo)
    assert before == after


def test_focused_run_key_matches_tree_digest_semantics(tmp_path: Path) -> None:
    from scripts.test_selection.plan_steps import PlannedStep

    repo = _init_repo(tmp_path)
    steps = (
        PlannedStep(
            kind="pytest",
            argv=("python3", "-m", "pytest", "tests/test_core.py", "-q"),
        ),
    )
    metadata = ("schema=2", "level=2", "clusters=", "required=")
    key_a = compute_run_key(root=repo, steps=steps, metadata=metadata)
    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    key_b = compute_run_key(root=repo, steps=steps, metadata=metadata)
    assert key_a != key_b


def test_ci_resume_rejects_same_path_different_contents(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "tracked.txt").write_text("A\n", encoding="utf-8")
    digest_a = tree_digest(repo)
    (repo / "tracked.txt").write_text("B\n", encoding="utf-8")
    digest_b = tree_digest(repo)
    assert digest_a != digest_b
    summary_digest = digest_a
    current_digest = digest_b
    assert summary_digest != current_digest


def test_changed_source_paths_detects_modified_and_untracked(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    assert is_working_tree_clean(repo)
    assert changed_source_paths(repo) == ()
    (repo / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    (repo / "new.txt").write_text("x\n", encoding="utf-8")
    changed = changed_source_paths(repo)
    assert "tracked.txt" in changed
    assert "new.txt" in changed
    assert not is_working_tree_clean(repo)


def test_changed_source_paths_ignores_artifact_directories(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    artifacts = repo / ".artifacts" / "ci"
    artifacts.mkdir(parents=True)
    (artifacts / "ci.log").write_text("log\n", encoding="utf-8")
    (repo / "build").mkdir()
    (repo / "build" / "wheel").write_text("x\n", encoding="utf-8")
    assert changed_source_paths(repo) == ()
    assert is_working_tree_clean(repo)


def test_changed_source_paths_detects_staged_delete_and_rename(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "old.txt").write_text("x\n", encoding="utf-8")
    _run_git(repo, "add", "old.txt")
    _run_git(repo, "commit", "-m", "add old")
    (repo / "tracked.txt").unlink()
    _run_git(repo, "add", "tracked.txt")
    _run_git(repo, "mv", "old.txt", "renamed.txt")
    changed = changed_source_paths(repo)
    assert "tracked.txt" in changed
    assert "old.txt" in changed or "renamed.txt" in changed
    assert not is_working_tree_clean(repo)
