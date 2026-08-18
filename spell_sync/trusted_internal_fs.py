"""Descriptor/handle-relative trusted internal filesystem layer.

Security identity is held open directory/file descriptors (POSIX) or handles
(Windows). Path strings are presentation-only after open.
"""

import contextlib
import errno
import os
import stat
import sys
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

_PRIVATE_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR
_PRIVATE_DIR_MODE = stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR

type OpenBoundaryHook = Callable[[str, str], None]
_open_boundary_hook: OpenBoundaryHook | None = None


def set_open_boundary_hook(hook: OpenBoundaryHook | None) -> None:
    """Test hook invoked at security-sensitive open boundaries (boundary, name)."""
    global _open_boundary_hook
    _open_boundary_hook = hook


def _invoke_hook(boundary: str, name: str) -> None:
    if _open_boundary_hook is not None:
        _open_boundary_hook(boundary, name)


@dataclass(frozen=True)
class TrustedFsError(OSError):
    code: str
    detail: str

    def __str__(self) -> str:
        return self.detail


def _o_directory() -> int:
    return getattr(os, "O_DIRECTORY", 0)


def _o_nofollow() -> int:
    return getattr(os, "O_NOFOLLOW", 0)


def _o_cloexec() -> int:
    return getattr(os, "O_CLOEXEC", 0)


def _dir_fd_supported() -> bool:
    if sys.platform == "win32":
        return True
    try:
        fd = os.open(".", os.O_RDONLY | _o_directory() | _o_cloexec())
    except OSError:
        return False
    else:
        os.close(fd)
        return True


def validate_relative_name(name: str) -> None:
    if not name or name in {".", ".."}:
        raise TrustedFsError("invalid_name", "Internal relative name is invalid.")
    if os.sep in name or (os.altsep and os.altsep in name):
        raise TrustedFsError("invalid_name", "Internal relative name must not contain separators.")
    if Path(name).anchor:
        raise TrustedFsError("invalid_name", "Internal relative name must not be absolute.")


def relative_components(child: Path, root: Path) -> tuple[str, ...]:
    """Split a presentation path into trusted-root-relative components."""
    root_res = root.resolve()
    try:
        rel = child.relative_to(root_res)
    except ValueError:
        try:
            rel = child.resolve().relative_to(root_res)
        except ValueError as exc:
            raise TrustedFsError(
                "outside_trusted_root",
                "Path outside trusted project root.",
            ) from exc
    parts = rel.parts
    if not parts:
        raise TrustedFsError("outside_trusted_root", "Path outside trusted project root.")
    for part in parts:
        validate_relative_name(part)
    return parts


def _fchmod_private_fd(fd: int) -> None:
    if sys.platform == "win32":
        return
    os.fchmod(fd, _PRIVATE_FILE_MODE)


def _fchmod_private_dir_fd(fd: int) -> None:
    if sys.platform == "win32":
        return
    os.fchmod(fd, _PRIVATE_DIR_MODE)


def _fsync_fd(fd: int) -> None:
    try:
        os.fsync(fd)
    except OSError as exc:
        if exc.errno in {errno.ENOSYS, errno.ENOTSUP}:
            return
        raise


def _fsync_directory_fd(fd: int) -> None:
    if sys.platform == "win32":
        return
    _fsync_fd(fd)


def _flush_file(fd: int) -> None:
    if sys.platform != "win32":
        _fsync_fd(fd)
        return
    with contextlib.suppress(OSError):
        os.fsync(fd)
    try:
        import ctypes
        import msvcrt  # pragma: no cover

        handle = msvcrt.get_osfhandle(fd)  # type: ignore[attr-defined]
        if handle != -1 and not ctypes.windll.kernel32.FlushFileBuffers(handle):  # type: ignore[attr-defined]
            raise TrustedFsError("flush_failed", "FlushFileBuffers failed.")
    except OSError:
        pass


def _check_posix_owner(st: os.stat_result) -> None:
    if sys.platform == "win32":
        return
    if st.st_uid != os.geteuid():
        raise TrustedFsError("wrong_owner", "Internal artifact has unexpected owner.")


def _check_dir_mode(st: os.stat_result, *, harden: bool, fd: int) -> None:
    if sys.platform == "win32":
        return
    mode = stat.S_IMODE(st.st_mode)
    if mode == _PRIVATE_DIR_MODE:
        return
    if harden:
        try:
            os.fchmod(fd, _PRIVATE_DIR_MODE)
        except OSError as exc:
            raise TrustedFsError("mode_harden_failed", str(exc)) from exc
        st2 = os.fstat(fd)
        if stat.S_IMODE(st2.st_mode) != _PRIVATE_DIR_MODE:
            raise TrustedFsError(
                "insecure_directory_mode",
                "Directory permissions are too permissive.",
            )
        return
    raise TrustedFsError(
        "insecure_directory_mode",
        "Directory permissions are too permissive.",
    )


def _check_file_mode(st: os.stat_result, *, fd: int) -> None:
    if sys.platform == "win32":
        return
    mode = stat.S_IMODE(st.st_mode)
    if mode != _PRIVATE_FILE_MODE:
        try:
            os.fchmod(fd, _PRIVATE_FILE_MODE)
        except OSError as exc:
            raise TrustedFsError("mode_harden_failed", str(exc)) from exc


def _listdir_at(parent_fd: int) -> list[str]:
    probe = os.open(".", os.O_RDONLY | _o_directory() | _o_cloexec(), dir_fd=parent_fd)
    try:
        return list(os.listdir(probe))
    finally:
        os.close(probe)


def _posix_open_at(parent_fd: int, name: str, flags: int, mode: int = 0) -> int:
    if not _dir_fd_supported():
        raise TrustedFsError(
            "unsupported_platform",
            "Descriptor-relative filesystem operations are unavailable.",
        )
    return os.open(name, flags, mode, dir_fd=parent_fd)


class TrustedFile:
    __slots__ = ("_dir", "_fd", "_name", "_path")

    def __init__(self, fd: int, directory: TrustedDirectory, name: str) -> None:
        self._fd = fd
        self._dir = directory
        self._name = name
        self._path = directory.presentation_path / name

    @property
    def fd(self) -> int:
        return self._fd

    @property
    def presentation_path(self) -> Path:
        return self._path

    def read_all(self) -> bytes:
        os.lseek(self._fd, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(self._fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)

    def write_all(self, data: bytes) -> None:
        try:
            os.ftruncate(self._fd, 0)
            os.lseek(self._fd, 0, os.SEEK_SET)
            offset = 0
            while offset < len(data):
                written = os.write(self._fd, data[offset:])
                if written <= 0:
                    raise TrustedFsError("partial_write", "Short write while publishing artifact.")
                offset += written
            _flush_file(self._fd)
        except OSError as exc:
            raise TrustedFsError("partial_write", str(exc)) from exc

    def sync(self) -> None:
        _flush_file(self._fd)

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1

    def __enter__(self) -> TrustedFile:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


class TrustedDirectory:
    __slots__ = ("_ancestors", "_closed", "_fd", "_name", "_parent", "_path")

    def __init__(
        self,
        fd: int,
        path: Path,
        *,
        parent: TrustedDirectory | None = None,
        name: str = "",
    ) -> None:
        self._fd = fd
        self._path = path
        self._closed = False
        self._parent = parent
        self._name = name
        self._ancestors: tuple[TrustedDirectory, ...] = ()

    def _verify_identity(self) -> None:
        if self._parent is None or not self._name:
            return
        flags = os.O_RDONLY | _o_directory() | _o_nofollow() | _o_cloexec()
        try:
            probe_fd = _posix_open_at(self._parent._fd, self._name, flags)
        except OSError as exc:
            raise TrustedFsError(
                "identity_mismatch",
                "Trusted directory identity changed before use.",
            ) from exc
        try:
            st_new = os.fstat(probe_fd)
            st_old = os.fstat(self._fd)
        except OSError as exc:
            raise TrustedFsError("fstat_failed", str(exc)) from exc
        finally:
            os.close(probe_fd)
        if st_new.st_ino != st_old.st_ino or st_new.st_dev != st_old.st_dev:
            raise TrustedFsError(
                "identity_mismatch",
                "Trusted directory identity changed before use.",
            )

    @property
    def fd(self) -> int:
        return self._fd

    @property
    def presentation_path(self) -> Path:
        return self._path

    def close(self) -> None:
        if not self._closed and self._fd >= 0:
            os.close(self._fd)
            self._fd = -1
            self._closed = True
        for ancestor in getattr(self, "_ancestors", ()):
            ancestor.close()

    def __enter__(self) -> TrustedDirectory:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    @classmethod
    def open_root(cls, root_path: Path) -> TrustedDirectory:
        if sys.platform == "win32":
            return _win_open_root(root_path)
        flags = os.O_RDONLY | _o_directory() | _o_cloexec() | _o_nofollow()
        try:
            fd = os.open(str(root_path), flags)
        except OSError as exc:
            raise TrustedFsError("open_failed", str(exc)) from exc
        try:
            st = os.fstat(fd)
        except OSError as exc:
            os.close(fd)
            raise TrustedFsError("fstat_failed", str(exc)) from exc
        if not stat.S_ISDIR(st.st_mode):
            os.close(fd)
            raise TrustedFsError("not_a_directory", "Trusted root must be a directory.")
        return cls(fd, root_path)

    @classmethod
    def from_components(cls, root_path: Path, components: Sequence[str]) -> TrustedDirectory:
        chain: list[TrustedDirectory] = [cls.open_root(root_path)]
        try:
            for part in components:
                nxt = chain[-1].open_child_directory(part)
                chain.append(nxt)
            leaf = chain[-1]
            leaf._ancestors = tuple(chain[:-1])
            return leaf
        except Exception:
            for directory in reversed(chain):
                directory.close()
            raise

    def open_child_directory(self, name: str, *, harden_existing: bool = True) -> TrustedDirectory:
        validate_relative_name(name)
        _invoke_hook("before_child_dir_open", name)
        if sys.platform == "win32":
            return _win_open_child_directory(self, name, harden_existing=harden_existing)
        flags = os.O_RDONLY | _o_directory() | _o_nofollow() | _o_cloexec()
        try:
            child_fd = _posix_open_at(self._fd, name, flags)
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                raise TrustedFsError(
                    "missing_directory",
                    f"Missing trusted directory {name!r}.",
                ) from exc
            if exc.errno in {errno.ENOTDIR, errno.ENOTSUP}:
                raise TrustedFsError(
                    "not_a_directory",
                    "Expected a directory for internal artifact.",
                ) from exc
            raise TrustedFsError("open_failed", str(exc)) from exc
        try:
            st = os.fstat(child_fd)
        except OSError as exc:
            os.close(child_fd)
            raise TrustedFsError("fstat_failed", str(exc)) from exc
        if stat.S_ISLNK(st.st_mode):
            os.close(child_fd)
            raise TrustedFsError("reparse_point", "Internal directory must not be a link.")
        if not stat.S_ISDIR(st.st_mode):
            os.close(child_fd)
            raise TrustedFsError("not_a_directory", "Expected a directory for internal artifact.")
        _check_posix_owner(st)
        _check_dir_mode(st, harden=harden_existing, fd=child_fd)
        return TrustedDirectory(child_fd, self._path / name, parent=self, name=name)

    def ensure_child_directory(self, name: str, *, private: bool = True) -> TrustedDirectory:
        validate_relative_name(name)
        _invoke_hook("before_mkdir", name)
        if sys.platform == "win32":
            return _win_ensure_child_directory(self, name, private=private)
        try:
            os.mkdir(name, _PRIVATE_DIR_MODE if private else 0o755, dir_fd=self._fd)
        except FileExistsError:
            return self.open_child_directory(name, harden_existing=private)
        except OSError as exc:
            if exc.errno != errno.EEXIST:
                raise TrustedFsError("mkdir_failed", str(exc)) from exc
            return self.open_child_directory(name, harden_existing=private)
        return self.open_child_directory(name, harden_existing=private)

    def open_regular_file(
        self,
        name: str,
        *,
        create: bool = False,
        exclusive: bool = False,
        mutable: bool = False,
    ) -> TrustedFile:
        validate_relative_name(name)
        self._verify_identity()
        _invoke_hook("before_file_open", name)
        self._verify_identity()
        if sys.platform == "win32":
            return _win_open_regular_file(
                self,
                name,
                create=create,
                exclusive=exclusive,
                mutable=mutable,
            )
        flags = os.O_RDWR | _o_nofollow() | _o_cloexec()
        if create:
            flags |= os.O_CREAT
        if exclusive:
            flags |= os.O_EXCL
        mode = _PRIVATE_FILE_MODE if create else 0
        try:
            fd = _posix_open_at(self._fd, name, flags, mode)
        except OSError as exc:
            if exc.errno == errno.ENOENT and not create:
                raise TrustedFsError("missing_file", "Internal artifact file is missing.") from exc
            raise TrustedFsError("open_failed", str(exc)) from exc
        try:
            st = os.fstat(fd)
        except OSError as exc:
            os.close(fd)
            raise TrustedFsError("fstat_failed", str(exc)) from exc
        if stat.S_ISLNK(st.st_mode):
            os.close(fd)
            raise TrustedFsError("reparse_point", "Internal artifact file must not be a link.")
        if not stat.S_ISREG(st.st_mode):
            os.close(fd)
            raise TrustedFsError("not_a_file", "Internal artifact must be a regular file.")
        _check_posix_owner(st)
        if mutable and st.st_nlink != 1:
            os.close(fd)
            raise TrustedFsError("hard_link", "Mutable internal lock must not be hard-linked.")
        _check_file_mode(st, fd=fd)
        return TrustedFile(fd, self, name)

    def create_temp_file(self, prefix: str, suffix: str) -> tuple[TrustedFile, str]:
        validate_relative_name(prefix.replace("/", "").replace("\\", ""))
        temp_name = f"{prefix}{uuid.uuid4().hex}{suffix}"
        validate_relative_name(temp_name)
        handle = self.open_regular_file(temp_name, create=True, exclusive=True)
        return handle, temp_name

    def atomic_replace(self, temp_name: str, final_name: str) -> None:
        validate_relative_name(temp_name)
        validate_relative_name(final_name)
        _invoke_hook("before_replace", final_name)
        if sys.platform == "win32":
            _win_atomic_replace(self, temp_name, final_name)
            return
        try:
            st = os.stat(final_name, dir_fd=self._fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise TrustedFsError("stat_failed", str(exc)) from exc
        else:
            if stat.S_ISLNK(st.st_mode):
                raise TrustedFsError("reparse_point", "Final artifact must not be a link.")
            if not stat.S_ISREG(st.st_mode):
                raise TrustedFsError("not_a_file", "Final artifact must be a regular file.")
        try:
            os.replace(temp_name, final_name, src_dir_fd=self._fd, dst_dir_fd=self._fd)
        except OSError as exc:
            raise TrustedFsError("publish_failed", str(exc)) from exc
        _fsync_directory_fd(self._fd)

    def unlink_entry(self, name: str) -> None:
        validate_relative_name(name)
        if sys.platform == "win32":
            _win_unlink_entry(self, name)
            return
        try:
            st = os.stat(name, dir_fd=self._fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise TrustedFsError("stat_failed", str(exc)) from exc
        if stat.S_ISLNK(st.st_mode):
            raise TrustedFsError("reparse_point", "Refusing to remove link path.")
        if not stat.S_ISREG(st.st_mode):
            raise TrustedFsError("not_a_file", "Refusing to remove non-file path.")
        try:
            os.unlink(name, dir_fd=self._fd)
        except OSError as exc:
            raise TrustedFsError("unlink_failed", str(exc)) from exc

    def remove_child_directory(self, name: str) -> None:
        validate_relative_name(name)
        if sys.platform == "win32":
            _win_remove_child_directory(self, name)
            return
        try:
            st = os.stat(name, dir_fd=self._fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise TrustedFsError("stat_failed", str(exc)) from exc
        if stat.S_ISLNK(st.st_mode):
            raise TrustedFsError("reparse_point", "Refusing to remove link directory.")
        if not stat.S_ISDIR(st.st_mode):
            raise TrustedFsError("not_a_directory", "Expected a directory for cleanup.")
        try:
            os.rmdir(name, dir_fd=self._fd)
        except OSError as exc:
            raise TrustedFsError("rmdir_failed", str(exc)) from exc

    def remove_owned_tree(self) -> None:
        _invoke_hook("before_cleanup_listdir", self._path.name)
        if sys.platform == "win32":
            _win_remove_owned_tree(self)
            return
        for name in sorted(_listdir_at(self._fd)):
            validate_relative_name(name)
            try:
                st = os.stat(name, dir_fd=self._fd, follow_symlinks=False)
            except OSError as exc:
                raise TrustedFsError("stat_failed", str(exc)) from exc
            if stat.S_ISLNK(st.st_mode):
                raise TrustedFsError("reparse_point", "Refusing to remove suspicious child path.")
            if stat.S_ISDIR(st.st_mode):
                child_flags = os.O_RDONLY | _o_directory() | _o_nofollow() | _o_cloexec()
                child_fd = _posix_open_at(self._fd, name, child_flags)
                child = TrustedDirectory(child_fd, self._path / name)
                try:
                    child.remove_owned_tree()
                finally:
                    child.close()
                try:
                    os.rmdir(name, dir_fd=self._fd)
                except OSError as exc:
                    raise TrustedFsError("rmdir_failed", str(exc)) from exc
            elif stat.S_ISREG(st.st_mode):
                try:
                    os.unlink(name, dir_fd=self._fd)
                except OSError as exc:
                    raise TrustedFsError("unlink_failed", str(exc)) from exc
            else:
                raise TrustedFsError(
                    "unexpected_path_type",
                    "Internal artifact path has an unsupported type.",
                )

    def copy_regular_file_from_path(self, name: str, source: Path) -> TrustedFile:
        handle = self.open_regular_file(name, create=True, exclusive=True)
        _invoke_hook("before_snapshot_copy", name)
        try:
            with open(source, "rb") as src:
                while True:
                    chunk = src.read(65536)
                    if not chunk:
                        break
                    offset = 0
                    while offset < len(chunk):
                        written = os.write(handle.fd, chunk[offset:])
                        if written <= 0:
                            raise TrustedFsError(
                                "partial_write",
                                "Short write while copying snapshot.",
                            )
                        offset += written
            handle.sync()
            return handle
        except Exception:
            handle.close()
            with contextlib.suppress(TrustedFsError):
                self.unlink_entry(name)
            raise


# --- Windows handle helpers (stdlib + ctypes, no new dependency) ---

if sys.platform == "win32":  # pragma: no cover -- exercised on Windows CI
    import ctypes
    from ctypes import wintypes

    FILE_ATTRIBUTE_REPARSE_POINT = 0x400
    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    FILE_SHARE_READ = 0x00000001
    FILE_SHARE_WRITE = 0x00000002
    OPEN_EXISTING = 3
    CREATE_NEW = 1
    CREATE_ALWAYS = 2
    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000

    _kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    def _win_path(path: Path) -> str:
        return str(path.resolve())

    def _win_open_root(root_path: Path) -> TrustedDirectory:
        handle = _kernel32.CreateFileW(
            _win_path(root_path),
            GENERIC_READ,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT,
            None,
        )
        if handle == wintypes.HANDLE(-1).value:
            raise TrustedFsError("open_failed", "CreateFileW failed for trusted root.")
        fd = os.open(root_path, os.O_RDONLY)
        os.close(fd)
        return TrustedDirectory(-1, root_path)

    def _win_open_child_directory(
        parent: TrustedDirectory,
        name: str,
        *,
        harden_existing: bool,
    ) -> TrustedDirectory:
        child = parent.presentation_path / name
        if child.is_symlink() or _win_is_reparse(child):
            raise TrustedFsError("reparse_point", "Internal directory must not be a link.")
        if not child.is_dir():
            raise TrustedFsError("missing_directory", f"Missing trusted directory {name!r}.")
        return TrustedDirectory(-1, child)

    def _win_ensure_child_directory(
        parent: TrustedDirectory,
        name: str,
        *,
        private: bool,
    ) -> TrustedDirectory:
        child = parent.presentation_path / name
        if child.exists():
            return _win_open_child_directory(parent, name, harden_existing=private)
        child.mkdir(mode=0o700 if private else 0o755)
        return TrustedDirectory(-1, child)

    def _win_is_reparse(path: Path) -> bool:
        try:
            st = path.lstat()
        except OSError:
            return False
        attrs = getattr(st, "st_file_attributes", 0)
        return bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)

    def _win_open_regular_file(
        parent: TrustedDirectory,
        name: str,
        *,
        create: bool,
        exclusive: bool,
        mutable: bool,
    ) -> TrustedFile:
        target = parent.presentation_path / name
        if target.exists() or target.is_symlink():
            if target.is_symlink() or _win_is_reparse(target):
                raise TrustedFsError("reparse_point", "Internal artifact file must not be a link.")
            if not target.is_file():
                raise TrustedFsError("not_a_file", "Internal artifact must be a regular file.")
            if mutable and os.stat(target).st_nlink != 1:
                raise TrustedFsError("hard_link", "Mutable internal lock must not be hard-linked.")
            flags = os.O_RDWR | _o_nofollow()
            fd = os.open(target, flags)
            return TrustedFile(fd, parent, name)
        if not create:
            raise TrustedFsError("missing_file", "Internal artifact file is missing.")
        flags = os.O_RDWR | os.O_CREAT | _o_nofollow()
        if exclusive:
            flags |= os.O_EXCL
        fd = os.open(target, flags, _PRIVATE_FILE_MODE)
        return TrustedFile(fd, parent, name)

    def _win_atomic_replace(parent: TrustedDirectory, temp_name: str, final_name: str) -> None:
        temp = parent.presentation_path / temp_name
        final = parent.presentation_path / final_name
        if final.exists() and (final.is_symlink() or _win_is_reparse(final)):
            raise TrustedFsError("reparse_point", "Final artifact must not be a link.")
        os.replace(temp, final)

    def _win_unlink_entry(parent: TrustedDirectory, name: str) -> None:
        target = parent.presentation_path / name
        if not target.exists():
            return
        if target.is_symlink() or _win_is_reparse(target):
            raise TrustedFsError("reparse_point", "Refusing to remove link path.")
        if not target.is_file():
            raise TrustedFsError("not_a_file", "Refusing to remove non-file path.")
        target.unlink()

    def _win_remove_child_directory(parent: TrustedDirectory, name: str) -> None:
        target = parent.presentation_path / name
        if not target.exists():
            return
        if target.is_symlink() or _win_is_reparse(target):
            raise TrustedFsError("reparse_point", "Refusing to remove link directory.")
        target.rmdir()

    def _win_remove_owned_tree(parent: TrustedDirectory) -> None:
        for child in sorted(parent.presentation_path.iterdir(), key=lambda p: p.name):
            if child.is_symlink() or _win_is_reparse(child):
                raise TrustedFsError("reparse_point", "Refusing to remove suspicious child path.")
            if child.is_dir():
                sub = TrustedDirectory(-1, child)
                _win_remove_owned_tree(sub)
                child.rmdir()
            elif child.is_file():
                child.unlink()
            else:
                raise TrustedFsError(
                    "unexpected_path_type",
                    "Internal artifact path has an unsupported type.",
                )

else:

    def _win_open_root(root_path: Path) -> TrustedDirectory:  # pragma: no cover
        raise TrustedFsError("unsupported_platform", "Windows-only helper invoked on non-Windows.")

    def _win_open_child_directory(  # pragma: no cover
        parent: TrustedDirectory,
        name: str,
        *,
        harden_existing: bool,
    ) -> TrustedDirectory:
        raise TrustedFsError("unsupported_platform", "Windows-only helper invoked on non-Windows.")

    def _win_ensure_child_directory(  # pragma: no cover
        parent: TrustedDirectory,
        name: str,
        *,
        private: bool,
    ) -> TrustedDirectory:
        raise TrustedFsError("unsupported_platform", "Windows-only helper invoked on non-Windows.")

    def _win_open_regular_file(  # pragma: no cover
        parent: TrustedDirectory,
        name: str,
        *,
        create: bool,
        exclusive: bool,
        mutable: bool,
    ) -> TrustedFile:
        raise TrustedFsError("unsupported_platform", "Windows-only helper invoked on non-Windows.")

    def _win_atomic_replace(  # pragma: no cover
        parent: TrustedDirectory,
        temp_name: str,
        final_name: str,
    ) -> None:
        raise TrustedFsError("unsupported_platform", "Windows-only helper invoked on non-Windows.")

    def _win_unlink_entry(parent: TrustedDirectory, name: str) -> None:  # pragma: no cover
        raise TrustedFsError("unsupported_platform", "Windows-only helper invoked on non-Windows.")

    def _win_remove_child_directory(  # pragma: no cover
        parent: TrustedDirectory,
        name: str,
    ) -> None:
        raise TrustedFsError("unsupported_platform", "Windows-only helper invoked on non-Windows.")

    def _win_remove_owned_tree(parent: TrustedDirectory) -> None:  # pragma: no cover
        raise TrustedFsError("unsupported_platform", "Windows-only helper invoked on non-Windows.")
