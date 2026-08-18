"""Secure filesystem operations for spell-sync internal artifacts.

Trust boundary: paths must stay under the project directory derived from the
wordlist. Authorization uses descriptor/handle-relative operations — path
strings are presentation-only after the trusted root is opened.
"""

import contextlib
import errno
import os
import stat
import sys
import uuid
from pathlib import Path

from .project import ProjectContext
from .trusted_internal_fs import (
    TrustedDirectory,
    TrustedFsError,
    relative_components,
    set_open_boundary_hook,
    validate_relative_name,
)

FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_PRIVATE_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR
_PRIVATE_DIR_MODE = stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR


class SecureArtifactError(TrustedFsError):
    """Fail-closed rejection or publication failure for an internal artifact."""


def _map_error(exc: TrustedFsError) -> SecureArtifactError:
    return SecureArtifactError(exc.code, exc.detail)


def trusted_project_root(wordlist: Path) -> Path:
    """Canonical project directory for internal artifact containment."""
    return ProjectContext.build(wordlist).project_dir


def trusted_project_root_resolved(wordlist: Path) -> Path:
    root = trusted_project_root(wordlist)
    try:
        return root.resolve()
    except OSError as exc:
        raise SecureArtifactError("trusted_root_unavailable", str(exc)) from exc


def is_reparse_point(path: Path) -> bool:
    """True when path is a symlink or Windows reparse point (including junction)."""
    try:
        if path.is_symlink():
            return True
        if sys.platform != "win32":
            return False
        st = path.lstat()
        attrs = getattr(st, "st_file_attributes", 0)
        return bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)
    except OSError:
        return False


def _with_root(root: Path) -> TrustedDirectory:
    try:
        return TrustedDirectory.open_root(root)
    except TrustedFsError as exc:
        raise _map_error(exc) from exc


def _directory_at(root: Path, path: Path) -> TrustedDirectory:
    parts = relative_components(path, root)
    try:
        return TrustedDirectory.from_components(root, parts)
    except TrustedFsError as exc:
        raise _map_error(exc) from exc


def _parent_directory_at(root: Path, path: Path) -> tuple[TrustedDirectory, str]:
    parts = _relative_parts(path, root)
    if len(parts) == 1:
        trusted = _with_root(root)
        return trusted, parts[0]
    parent = TrustedDirectory.from_components(root, parts[:-1])
    return parent, parts[-1]


def _relative_parts(child: Path, root: Path) -> tuple[str, ...]:
    try:
        return relative_components(child, root)
    except TrustedFsError as exc:
        raise _map_error(exc) from exc


def ensure_trusted_directory(path: Path, *, root: Path) -> None:
    """Create ``path`` under ``root`` without following existing links."""
    parts = _relative_parts(path, root)
    trusted = _with_root(root)
    try:
        for part in parts:
            try:
                nxt = trusted.ensure_child_directory(part, private=True)
            except TrustedFsError as exc:
                raise _map_error(exc) from exc
            trusted.close()
            trusted = nxt
    finally:
        trusted.close()


def open_trusted_regular_file(
    path: Path,
    *,
    root: Path,
    create: bool = False,
    mutable: bool = False,
) -> int:
    """Open a trusted regular file without following links."""
    parent, name = _parent_directory_at(root, path)
    try:
        handle = parent.open_regular_file(name, create=create, mutable=mutable)
        fd = handle.fd
        handle._fd = -1  # transfer ownership
        return fd
    except TrustedFsError as exc:
        raise _map_error(exc) from exc
    finally:
        parent.close()


def read_trusted_regular_file(path: Path, *, root: Path) -> bytes:
    """Read a trusted regular file via secure no-follow open."""
    parent, name = _parent_directory_at(root, path)
    try:
        with parent.open_regular_file(name, create=False) as handle:
            return handle.read_all()
    except TrustedFsError as exc:
        raise _map_error(exc) from exc
    finally:
        parent.close()


def atomic_write_trusted_file(path: Path, data: bytes, *, root: Path) -> None:
    """Publish ``data`` to ``path`` atomically with durability best effort."""
    parent, final_name = _parent_directory_at(root, path)
    temp_name = f".{final_name}.{uuid.uuid4().hex}.tmp"
    try:
        validate_relative_name(temp_name)
        with parent.open_regular_file(temp_name, create=True, exclusive=True) as temp:
            temp.write_all(data)
        parent.atomic_replace(temp_name, final_name)
    except TrustedFsError as exc:
        with contextlib.suppress(SecureArtifactError):
            parent.unlink_entry(temp_name)
        raise _map_error(exc) from exc
    finally:
        parent.close()


def remove_trusted_file(path: Path, *, root: Path) -> None:
    parent, name = _parent_directory_at(root, path)
    try:
        parent.unlink_entry(name)
    except TrustedFsError as exc:
        raise _map_error(exc) from exc
    finally:
        parent.close()


def remove_empty_trusted_directory(path: Path, *, root: Path) -> None:
    """Remove ``path`` when it is an empty trusted directory under ``root``."""
    parts = _relative_parts(path, root)
    if len(parts) == 1:
        parent = _with_root(root)
        name = parts[0]
    else:
        try:
            parent = TrustedDirectory.from_components(root, parts[:-1])
        except TrustedFsError as exc:
            raise _map_error(exc) from exc
        name = parts[-1]
    try:
        child = parent.open_child_directory(name)
        child.close()
        parent.remove_child_directory(name)
    except TrustedFsError as exc:
        if exc.code in {"missing_directory", "rmdir_failed"}:
            return
        raise _map_error(exc) from exc
    finally:
        parent.close()


def remove_trusted_tree(path: Path, *, root: Path) -> None:
    parts = _relative_parts(path, root)
    if len(parts) == 1:
        parent = _with_root(root)
        name = parts[0]
    else:
        try:
            parent = TrustedDirectory.from_components(root, parts[:-1])
        except TrustedFsError as exc:
            raise _map_error(exc) from exc
        name = parts[-1]
    try:
        try:
            target = parent.open_child_directory(name)
        except TrustedFsError as exc:
            if exc.code == "missing_directory":
                return
            raise _map_error(exc) from exc
        try:
            target.remove_owned_tree()
        finally:
            target.close()
        parent.remove_child_directory(name)
    except TrustedFsError as exc:
        raise _map_error(exc) from exc
    finally:
        parent.close()


def prepare_trusted_txn_root(wordlist: Path, transaction_id: str) -> Path:
    """Ensure ``.spell-sync.txn/<transaction_id>`` exists safely under the project."""
    root = trusted_project_root(wordlist)
    validate_relative_name(".spell-sync.txn")
    validate_relative_name(transaction_id)
    trusted = _with_root(root)
    try:
        txn_parent = trusted.ensure_child_directory(".spell-sync.txn", private=True)
        trusted.close()
        txn_dir = txn_parent.ensure_child_directory(transaction_id, private=True)
        presentation = txn_dir.presentation_path
        txn_dir.close()
        txn_parent.close()
        return presentation
    except TrustedFsError as exc:
        trusted.close()
        raise _map_error(exc) from exc


def copy_trusted_snapshot_file(
    snapshot_dir: Path,
    *,
    root: Path,
    base_name: str,
    source: Path,
) -> Path:
    """Create an exclusive snapshot under ``snapshot_dir`` and copy ``source`` via held fd."""
    snap_name = f"{base_name}.{uuid.uuid4().hex}.snap"
    parent = _directory_at(root, snapshot_dir)
    try:
        with parent.copy_regular_file_from_path(snap_name, source) as handle:
            presentation = handle.presentation_path
        return presentation
    except TrustedFsError as exc:
        raise _map_error(exc) from exc
    finally:
        parent.close()


def create_trusted_snapshot_file(snapshot_dir: Path, *, root: Path, base_name: str) -> Path:
    """Create an empty snapshot file exclusively under ``snapshot_dir``."""
    snap_name = f"{base_name}.{uuid.uuid4().hex}.snap"
    parent = _directory_at(root, snapshot_dir)
    try:
        with parent.open_regular_file(snap_name, create=True, exclusive=True) as handle:
            return handle.presentation_path
    except TrustedFsError as exc:
        raise _map_error(exc) from exc
    finally:
        parent.close()


# Re-export hook for adversarial tests.
__all__ = [
    "SecureArtifactError",
    "atomic_write_trusted_file",
    "copy_trusted_snapshot_file",
    "create_trusted_snapshot_file",
    "ensure_trusted_directory",
    "is_reparse_point",
    "open_trusted_regular_file",
    "prepare_trusted_txn_root",
    "read_trusted_regular_file",
    "remove_empty_trusted_directory",
    "remove_trusted_file",
    "remove_trusted_tree",
    "set_open_boundary_hook",
    "trusted_project_root",
    "trusted_project_root_resolved",
]


# Test helpers — fd-only private mode utilities.
def _fchmod_private(fd: int) -> None:
    if sys.platform == "win32":
        return
    with contextlib.suppress(OSError):
        os.fchmod(fd, _PRIVATE_FILE_MODE)


def _chmod_private_dir(path: Path) -> None:
    del path  # path-based chmod forbidden in secure layer; test patch point only


def _fsync_fd(fd: int) -> None:
    try:
        os.fsync(fd)
    except OSError as exc:
        if exc.errno in {errno.ENOSYS, errno.ENOTSUP}:
            return
        raise


def _fsync_directory(path: Path) -> None:
    if sys.platform == "win32":
        return
    flags = os.O_RDONLY
    dir_fd = getattr(os, "O_DIRECTORY", 0)
    if dir_fd:
        flags |= dir_fd
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        if exc.errno in {errno.ENOSYS, errno.ENOTSUP, errno.EISDIR}:
            return
        raise
    try:
        _fsync_fd(fd)
    finally:
        os.close(fd)


def _flush_file_windows(fd: int) -> None:
    from .trusted_internal_fs import _flush_file

    _flush_file(fd)


def _relative_under_root(path: Path, root: Path) -> Path:
    parts = _relative_parts(path, root)
    return Path(*parts)


def _reject_unsafe_component(path: Path) -> None:
    if not path.exists():
        return
    if is_reparse_point(path):
        raise SecureArtifactError("reparse_point", "Internal artifact path must not be a link.")
    if path.is_dir() and not path.is_symlink():
        return
    if path.is_file() and not path.is_symlink():
        return
    raise SecureArtifactError(
        "unexpected_path_type",
        "Internal artifact path has an unsupported type.",
    )
