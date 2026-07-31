"""Secure filesystem operations for spell-sync internal artifacts.

Trust boundary: paths must stay under the project directory derived from the
wordlist. Existing symlink, junction, and reparse-point components are rejected
fail-closed. Publication uses exclusive temp files, fsync, atomic replace, and
parent-directory sync on POSIX where available.
"""

from __future__ import annotations

import errno
import os
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .project import ProjectContext

FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_PRIVATE_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR
_PRIVATE_DIR_MODE = stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR


@dataclass(frozen=True)
class SecureArtifactError(OSError):
    """Fail-closed rejection or publication failure for an internal artifact."""

    code: str
    detail: str

    def __str__(self) -> str:
        return self.detail


def trusted_project_root(wordlist: Path) -> Path:
    """Canonical project directory for internal artifact containment."""
    return ProjectContext.build(wordlist).project_dir


def trusted_project_root_resolved(wordlist: Path) -> Path:
    root = trusted_project_root(wordlist)
    try:
        return root.resolve()
    except OSError as exc:
        raise SecureArtifactError("trusted_root_unavailable", str(exc)) from exc


def _relative_under_root(path: Path, root: Path) -> Path:
    try:
        root_resolved = root.resolve()
        path_resolved = path.resolve()
        return path_resolved.relative_to(root_resolved)
    except (OSError, ValueError) as exc:
        raise SecureArtifactError(
            "outside_trusted_root",
            "Path outside trusted project root.",
        ) from exc


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


def _verify_parent_chain(path: Path, root: Path) -> None:
    root = root.resolve()
    current = root
    try:
        relative = path.resolve().relative_to(root)
    except (OSError, ValueError) as exc:
        raise SecureArtifactError(
            "outside_trusted_root",
            "Path outside trusted project root.",
        ) from exc
    for part in relative.parts[:-1] if relative.parts else ():
        current = current / part
        _reject_unsafe_component(current)


def _fchmod_private(fd: int) -> None:
    if sys.platform == "win32":
        return
    try:
        os.fchmod(fd, _PRIVATE_FILE_MODE)
    except OSError:
        pass


def _chmod_private_dir(path: Path) -> None:
    if sys.platform == "win32":
        return
    try:
        os.chmod(path, _PRIVATE_DIR_MODE)
    except OSError:
        pass


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
    if sys.platform != "win32":
        return
    try:
        import msvcrt  # pragma: no cover

        os.fsync(fd)
    except OSError:
        try:
            import ctypes  # pragma: no cover

            handle = msvcrt.get_osfhandle(fd)  # type: ignore[attr-defined]
            if handle != -1:
                ctypes.windll.kernel32.FlushFileBuffers(handle)  # type: ignore[attr-defined]
        except OSError:
            pass


def ensure_trusted_directory(path: Path, *, root: Path) -> None:
    """Create ``path`` under ``root`` without following existing links."""
    _relative_under_root(path, root)
    current = root.resolve()
    relative = path.resolve().relative_to(current)
    for part in relative.parts:
        current = current / part
        if current.exists():
            _reject_unsafe_component(current)
            if not current.is_dir():
                raise SecureArtifactError(
                    "not_a_directory",
                    "Expected a directory for internal artifact.",
                )
            continue
        try:
            os.mkdir(current, mode=_PRIVATE_DIR_MODE)
        except OSError as exc:
            if exc.errno != errno.EEXIST:
                raise SecureArtifactError("mkdir_failed", str(exc)) from exc
            if not current.is_dir():
                raise SecureArtifactError(
                    "not_a_directory",
                    "Expected a directory for internal artifact.",
                ) from exc
        _chmod_private_dir(current)


def _validate_existing_regular_file(path: Path, *, root: Path) -> None:
    _verify_parent_chain(path, root)
    if not path.exists():
        return
    if is_reparse_point(path):
        raise SecureArtifactError("reparse_point", "Internal artifact file must not be a link.")
    if path.is_dir():
        raise SecureArtifactError("not_a_file", "Expected a regular file for internal artifact.")
    if not path.is_file():
        raise SecureArtifactError(
            "unexpected_path_type",
            "Internal artifact file has an unsupported type.",
        )


def open_trusted_regular_file(
    path: Path,
    *,
    root: Path,
    create: bool = False,
) -> int:
    """Open a trusted regular file without following links."""
    _verify_parent_chain(path, root)
    if path.exists():
        _validate_existing_regular_file(path, root=root)
    elif not create:
        raise SecureArtifactError("missing_file", "Internal artifact file is missing.")
    else:
        ensure_trusted_directory(path.parent, root=root)

    flags = os.O_RDWR
    if create:
        flags |= os.O_CREAT
    if sys.platform != "win32":
        flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, _PRIVATE_FILE_MODE)
    except OSError as exc:
        raise SecureArtifactError("open_failed", str(exc)) from exc

    try:
        st = os.fstat(fd)
    except OSError as exc:
        os.close(fd)
        raise SecureArtifactError("fstat_failed", str(exc)) from exc
    if not stat.S_ISREG(st.st_mode):
        os.close(fd)
        raise SecureArtifactError("not_a_file", "Internal artifact must be a regular file.")
    _fchmod_private(fd)
    return fd


def atomic_write_trusted_file(path: Path, data: bytes, *, root: Path) -> None:
    """Publish ``data`` to ``path`` atomically with durability best effort."""
    ensure_trusted_directory(path.parent, root=root)
    _validate_existing_regular_file(path, root=root)

    prefix = f".{path.name}."
    suffix = ".tmp"
    temp_fd: int | None = None
    temp_path: Path | None = None
    try:
        temp_fd, temp_name = tempfile.mkstemp(
            prefix=prefix,
            suffix=suffix,
            dir=str(path.parent),
        )
        temp_path = Path(temp_name)
        if sys.platform != "win32":
            _fchmod_private(temp_fd)
        try:
            offset = 0
            while offset < len(data):
                written = os.write(temp_fd, data[offset:])
                if written <= 0:
                    raise SecureArtifactError(
                        "partial_write",
                        "Short write while publishing artifact.",
                    )
                offset += written
            _fsync_fd(temp_fd)
            _flush_file_windows(temp_fd)
        finally:
            os.close(temp_fd)
            temp_fd = None

        if path.exists():
            _validate_existing_regular_file(path, root=root)
        os.replace(temp_path, path)
        temp_path = None
        if sys.platform != "win32":
            try:
                os.chmod(path, _PRIVATE_FILE_MODE)
            except OSError:
                pass
        _fsync_directory(path.parent)
    except OSError as exc:
        if isinstance(exc, SecureArtifactError):
            raise
        raise SecureArtifactError("publish_failed", str(exc)) from exc
    finally:
        if temp_fd is not None:
            try:
                os.close(temp_fd)
            except OSError:
                pass
        if temp_path is not None:
            try:
                if temp_path.exists() and temp_path.is_file() and not is_reparse_point(temp_path):
                    temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def remove_trusted_file(path: Path, *, root: Path) -> None:
    _validate_existing_regular_file(path, root=root)
    if not path.exists():
        return
    if is_reparse_point(path):
        raise SecureArtifactError("reparse_point", "Refusing to remove link path.")
    if not path.is_file():
        raise SecureArtifactError("not_a_file", "Refusing to remove non-file path.")
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise SecureArtifactError("unlink_failed", str(exc)) from exc


def remove_trusted_tree(path: Path, *, root: Path) -> None:
    _relative_under_root(path, root)
    if is_reparse_point(path):
        raise SecureArtifactError("reparse_point", "Refusing to remove link directory.")
    if not path.exists():
        return
    if not path.is_dir():
        raise SecureArtifactError("not_a_directory", "Expected a directory for cleanup.")
    for child in sorted(path.iterdir(), key=lambda p: p.name):
        if child.is_dir() and not child.is_symlink() and not is_reparse_point(child):
            remove_trusted_tree(child, root=root)
        elif child.is_file() and not is_reparse_point(child):
            remove_trusted_file(child, root=root)
        else:
            raise SecureArtifactError("reparse_point", "Refusing to remove suspicious child path.")
    try:
        path.rmdir()
    except OSError as exc:
        raise SecureArtifactError("rmdir_failed", str(exc)) from exc


def prepare_trusted_txn_root(wordlist: Path, transaction_id: str) -> Path:
    """Ensure ``.spell-sync.txn/<transaction_id>`` exists safely under the project."""
    root = trusted_project_root(wordlist)
    txn_parent = root / ".spell-sync.txn"
    txn_dir = txn_parent / transaction_id
    ensure_trusted_directory(txn_parent, root=root)
    if txn_dir.exists():
        if is_reparse_point(txn_dir) or not txn_dir.is_dir():
            raise SecureArtifactError("invalid_txn_root", "Transaction snapshot root is unsafe.")
    else:
        ensure_trusted_directory(txn_dir, root=root)
    return txn_dir


def create_trusted_snapshot_file(snapshot_dir: Path, *, root: Path, base_name: str) -> Path:
    """Create an empty snapshot file exclusively under ``snapshot_dir``."""
    ensure_trusted_directory(snapshot_dir, root=root)
    prefix = f"{base_name}."
    suffix = ".snap"
    temp_fd, temp_name = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=str(snapshot_dir))
    os.close(temp_fd)
    snap_path = Path(temp_name)
    if sys.platform != "win32":
        try:
            os.chmod(snap_path, _PRIVATE_FILE_MODE)
        except OSError:
            pass
    return snap_path
