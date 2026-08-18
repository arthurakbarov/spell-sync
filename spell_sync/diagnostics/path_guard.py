"""Validate configured diagnostic paths before read or write."""

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PathCheckResult:
    ok: bool
    detail: str | None = None


def _resolved_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except OSError, ValueError:
        return False


def validate_directory_path(path: Path, *, root: Path) -> PathCheckResult:
    if path.exists() and path.is_file():
        return PathCheckResult(False, "Expected a directory but found a file.")
    if path.exists() and path.is_symlink():
        return PathCheckResult(False, "Configured directory path must not be a symlink.")
    if path.exists() and not _resolved_under(path, root):
        return PathCheckResult(False, "Directory resolves outside configured root.")
    return PathCheckResult(True)


def validate_file_path(path: Path, *, root: Path) -> PathCheckResult:
    if path.exists() and path.is_dir():
        return PathCheckResult(False, "Expected a file but found a directory.")
    parent = path.parent
    if parent.exists() and parent.is_file():
        return PathCheckResult(False, "Parent path is a file.")
    if path.exists() and path.is_symlink():
        return PathCheckResult(False, "Configured file path must not be a symlink.")
    if path.exists() and not _resolved_under(path, root):
        return PathCheckResult(False, "File resolves outside configured root.")
    if parent.exists() and parent.is_symlink():
        return PathCheckResult(False, "Parent path must not be a symlink.")
    if parent.exists() and not _resolved_under(parent, root):
        return PathCheckResult(False, "Parent resolves outside configured root.")
    return PathCheckResult(True)


def open_append_only(path: Path, *, root: Path) -> tuple[int | None, str | None]:
    check = validate_file_path(path, root=root)
    if not check.ok:
        return None, check.detail
    parent = path.parent
    dir_check = validate_directory_path(parent, root=root)
    if not dir_check.ok:
        return None, dir_check.detail
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None, "unwritable"
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    if sys.platform != "win32":
        flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError:
        return None, "unwritable"
    return fd, None


def safe_unlink(path: Path, *, root: Path) -> PathCheckResult:
    check = validate_file_path(path, root=root)
    if not check.ok:
        return check
    if not path.is_file():
        return PathCheckResult(True)
    try:
        path.unlink()
    except OSError:
        return PathCheckResult(False, "remove failed")
    return PathCheckResult(True)
