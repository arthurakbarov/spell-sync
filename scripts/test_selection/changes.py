"""Detect changed files for test planning."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _git_lines(root: Path, *args: str) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _normalize_repo_path(path: str) -> str:
    return path.replace("\\", "/")


def collect_changed_files(
    root: Path,
    *,
    base: str | None = None,
    explicit_files: list[str] | None = None,
) -> list[str]:
    if explicit_files:
        return sorted({_normalize_repo_path(path) for path in explicit_files})

    changed: set[str] = set()

    if base and base != "HEAD":
        for line in _git_lines(root, "diff", "--name-only", base, "HEAD"):
            changed.add(_normalize_repo_path(line))
        for line in _git_lines(root, "diff", "--name-only", base):
            changed.add(_normalize_repo_path(line))
    else:
        for line in _git_lines(root, "diff", "--name-only", "HEAD"):
            changed.add(_normalize_repo_path(line))
        for line in _git_lines(root, "diff", "--name-only", "--cached"):
            changed.add(_normalize_repo_path(line))

    for line in _git_lines(
        root,
        "status",
        "--porcelain=v2",
        "--untracked-files=all",
    ):
        if line.startswith("? "):
            changed.add(_normalize_repo_path(line[2:].strip()))
            continue
        if line.startswith("1 ") or line.startswith("2 "):
            parts = line.split("\t", 1)
            if len(parts) == 2:
                changed.add(_normalize_repo_path(parts[1].strip()))
            continue
        if line.startswith("u "):
            parts = line.split("\t")
            if len(parts) >= 3:
                changed.add(_normalize_repo_path(parts[2].strip()))

    return sorted(changed)
