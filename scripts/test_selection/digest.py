"""Tree and configuration digests for test-run evidence keys."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from scripts.test_selection.tree_state import content_tree_digest, git_head

__all__ = [
    "compute_run_key",
    "config_digest",
    "content_tree_digest",
    "git_head",
    "python_version_digest",
    "tree_digest",
]


def tree_digest(root: Path, *, tracked_paths: list[str] | None = None) -> str:
    del tracked_paths
    return content_tree_digest(root)


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
    del tree_paths
    parts = [
        git_head(root),
        tree_digest(root),
        config_digest(root),
        python_version_digest(),
        "|".join(sorted(clusters)),
        "|".join(sorted(targets)),
        " ".join(command),
    ]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
