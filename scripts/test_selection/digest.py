"""Tree and configuration digests for test-run evidence keys."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path


def git_head(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip()


def git_status_digest(root: Path) -> str:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "status",
            "--porcelain=v2",
            "--untracked-files=all",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return "unknown"
    return hashlib.sha256(result.stdout.encode("utf-8")).hexdigest()


def file_content_digest(root: Path, relative_paths: list[str]) -> str:
    hasher = hashlib.sha256()
    for rel in sorted(set(relative_paths)):
        path = root / rel
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\0")
        if path.is_file():
            hasher.update(path.read_bytes())
        elif path.is_dir():
            hasher.update(b"<dir>")
        else:
            hasher.update(b"<missing>")
        hasher.update(b"\n")
    return hasher.hexdigest()


def tree_digest(root: Path, *, tracked_paths: list[str] | None = None) -> str:
    status = git_status_digest(root)
    head = git_head(root)
    if tracked_paths is None:
        content = status
    else:
        content = file_content_digest(root, tracked_paths)
    payload = f"{head}\n{status}\n{content}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def config_digest(root: Path) -> str:
    hasher = hashlib.sha256()
    for rel in ("pyproject.toml", "tests/test-impact.toml"):
        path = root / rel
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\0")
        if path.is_file():
            hasher.update(path.read_bytes())
        hasher.update(b"\n")
    return hasher.hexdigest()


def python_version_digest() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def compute_run_key(
    *,
    root: Path,
    command: list[str],
    targets: list[str],
    clusters: list[str],
    tree_paths: list[str] | None = None,
) -> str:
    parts = [
        git_head(root),
        tree_digest(root, tracked_paths=tree_paths),
        config_digest(root),
        python_version_digest(),
        "|".join(clusters),
        "|".join(sorted(targets)),
        " ".join(command),
    ]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
