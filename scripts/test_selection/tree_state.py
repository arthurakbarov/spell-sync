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

GIT_SUBPROCESS_TIMEOUT_SECONDS = 30.0


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
        timeout=GIT_SUBPROCESS_TIMEOUT_SECONDS,
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


def _decode_git_paths(raw: bytes) -> list[str]:
    if not raw:
        return []
    return [part.decode("utf-8", errors="surrogateescape") for part in raw.split(b"\0") if part]


def _paths_from_name_status(raw: bytes) -> list[str]:
    paths: list[str] = []
    index = 0
    parts = _decode_git_paths(raw)
    while index < len(parts):
        status = parts[index]
        index += 1
        if not status:
            continue
        if status.startswith("R") or status.startswith("C"):
            if index >= len(parts):
                break
            old_path = parts[index]
            index += 1
            if index >= len(parts):
                paths.append(old_path)
                break
            new_path = parts[index]
            index += 1
            paths.extend((old_path, new_path))
            continue
        if index >= len(parts):
            break
        paths.append(parts[index])
        index += 1
    return paths


def _collect_git_paths(root: Path, *args: str) -> list[str]:
    return _decode_git_paths(_run_git(root, *args))


def changed_source_paths(root: Path) -> tuple[str, ...]:
    """Return tracked/untracked source paths changed relative to HEAD."""
    paths: set[str] = set()
    paths.update(_collect_git_paths(root, "diff", "--name-only", "-z", "--cached", "HEAD"))
    paths.update(_collect_git_paths(root, "diff", "--name-only", "-z"))
    paths.update(_collect_git_paths(root, "ls-files", "-o", "--exclude-standard", "-z"))
    paths.update(_collect_git_paths(root, "ls-files", "-u", "-z"))
    paths.update(_paths_from_name_status(_run_git(root, "diff", "--name-status", "-z", "--cached")))
    paths.update(_paths_from_name_status(_run_git(root, "diff", "--name-status", "-z")))
    paths.update(
        _paths_from_name_status(_run_git(root, "diff", "--name-status", "-z", "--diff-filter=M"))
    )
    normalized = {normalize_rel(path) for path in paths if path}
    return tuple(sorted(path for path in normalized if not is_digest_excluded(path)))


def is_working_tree_clean(root: Path) -> bool:
    """True when no tracked or untracked source changes remain outside digest exclusions."""
    return not changed_source_paths(root)


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
    output = _run_git(root, "ls-files", "-o", "--exclude-standard", "-z")
    if not output:
        return []
    paths: list[str] = []
    for entry in output.split(b"\0"):
        if not entry:
            continue
        rel = entry.decode("utf-8", errors="replace")
        if rel and not is_digest_excluded(rel):
            paths.append(rel)
    return sorted(paths)


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
