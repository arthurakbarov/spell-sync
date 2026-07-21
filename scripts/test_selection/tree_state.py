"""Content-addressed git working-tree digest shared by ledger, CI, and resume checks."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

EXCLUDE_PREFIXES = (
    ".artifacts/",
    "build/",
    "dist/",
    "spell_sync.egg-info/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".coverage",
    "htmlcov/",
    "coverage.json",
)

EXCLUDE_EXACT = frozenset(
    {
        ".artifacts/ci/ci.log",
        ".artifacts/ci/ci-summary.json",
        ".artifacts/test-runs/current.json",
        ".artifacts/test-runs/index.json",
    }
)


def normalize_rel(path: str) -> str:
    return path.replace("\\", "/")


def is_digest_excluded(rel: str) -> bool:
    normalized = normalize_rel(rel)
    if normalized in EXCLUDE_EXACT:
        return True
    for prefix in EXCLUDE_PREFIXES:
        bare = prefix.rstrip("/")
        if normalized == bare or normalized.startswith(prefix):
            return True
    if normalized.endswith("/code.zip") or normalized == "code.zip":
        return True
    return False


def _run_git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        return b""
    return result.stdout


def git_head(root: Path) -> str:
    value = _run_git(root, "rev-parse", "HEAD").decode("utf-8", errors="replace").strip()
    return value or "unknown"


def git_branch(root: Path) -> str:
    branch = (
        _run_git(root, "symbolic-ref", "--short", "HEAD").decode("utf-8", errors="replace").strip()
    )
    if branch:
        return branch
    head = git_head(root)
    return f"detached:{head[:12]}"


def git_detached(root: Path) -> bool:
    return not _run_git(root, "symbolic-ref", "--quiet", "HEAD").strip()


def _status_paths(root: Path) -> list[str]:
    output = _run_git(root, "status", "--porcelain=v2", "--untracked-files=all").decode(
        "utf-8",
        errors="replace",
    )
    paths: list[str] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        paths.append(parts[1].strip())
    return paths


def is_working_tree_clean(root: Path) -> bool:
    """True when no tracked or untracked source changes remain outside digest exclusions."""
    for rel in _status_paths(root):
        normalized = normalize_rel(rel)
        if is_digest_excluded(normalized):
            continue
        return False
    return True


def _hash_path_entry(hasher: hashlib._Hash, rel: str, path: Path) -> None:
    hasher.update(rel.encode("utf-8"))
    hasher.update(b"\0")
    if path.is_symlink():
        hasher.update(b"symlink:")
        hasher.update(os.readlink(path).encode("utf-8", errors="replace"))
    elif path.is_file():
        mode = path.stat().st_mode & 0o777
        hasher.update(f"file:{mode:o}:".encode("utf-8"))
        hasher.update(path.read_bytes())
    elif path.is_dir():
        hasher.update(b"dir:")
    else:
        hasher.update(b"missing:")
    hasher.update(b"\n")


def _untracked_paths(root: Path) -> list[str]:
    output = _run_git(root, "ls-files", "-o", "--exclude-standard").decode(
        "utf-8",
        errors="replace",
    )
    paths = [line.strip() for line in output.splitlines() if line.strip()]
    return sorted(path for path in paths if not is_digest_excluded(path))


def content_tree_digest(root: Path) -> str:
    """Hash HEAD, branch, index/worktree diffs, and untracked file contents."""
    hasher = hashlib.sha256()
    hasher.update(b"head:")
    hasher.update(git_head(root).encode("utf-8"))
    hasher.update(b"\nbranch:")
    hasher.update(git_branch(root).encode("utf-8"))
    hasher.update(b"\nstaged:\n")
    hasher.update(_run_git(root, "diff", "--cached", "--binary", "HEAD"))
    hasher.update(b"\nunstaged:\n")
    hasher.update(_run_git(root, "diff", "--binary"))
    hasher.update(b"\nuntracked:\n")
    for rel in _untracked_paths(root):
        _hash_path_entry(hasher, rel, root / rel)
    return hasher.hexdigest()
