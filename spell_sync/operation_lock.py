"""Cross-platform project lock for spell-sync write operations."""

import json
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .project import ProjectContext
from .secure_artifacts import (
    SecureArtifactError,
    open_trusted_regular_file,
    trusted_project_root,
)


class OperationLockRejected(Exception):
    """Lock path is unsafe or cannot be opened securely."""

    def __init__(self, detail: str, *, code: str = "unsafe_lock") -> None:
        self.detail = detail
        self.code = code
        super().__init__(detail)


@dataclass(frozen=True)
class OperationLockInfo:
    pid: int
    started: str
    command: str
    wordlist: str


class OperationLocked(Exception):
    """Another live process holds the project lock."""

    def __init__(self, info: OperationLockInfo, lock_path: Path) -> None:
        self.info = info
        self.lock_path = lock_path
        super().__init__(
            f"operation locked by pid {info.pid} ({info.command}) since {info.started}"
        )


def lock_path_for_wordlist(wordlist: Path) -> Path:
    return ProjectContext.build(wordlist).project_dir / ".spell-sync.lock"


def lock_info_payload(info: OperationLockInfo) -> dict[str, object]:
    return asdict(info)


def _read_lock_info_fd(fd: int) -> OperationLockInfo | None:
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        raw_bytes = b""
        while True:
            chunk = os.read(fd, 4096)
            if not chunk:
                break
            raw_bytes += chunk
        raw = raw_bytes.decode("utf-8")
        data = json.loads(raw)
        return OperationLockInfo(
            pid=int(data["pid"]),
            started=str(data["started"]),
            command=str(data["command"]),
            wordlist=str(data["wordlist"]),
        )
    except OSError, json.JSONDecodeError, KeyError, TypeError, ValueError:
        return None


def _write_lock_info(fd: int, info: OperationLockInfo) -> None:
    payload = (json.dumps(asdict(info), ensure_ascii=False) + "\n").encode("utf-8")
    os.ftruncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, payload)


def _try_acquire_fd_win32(fd: int) -> bool:  # pragma: no cover
    import msvcrt

    try:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
    except OSError:
        return False
    return True


def _try_acquire_fd_unix(fd: int) -> bool:  # pragma: no cover
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined, misc]
    except BlockingIOError:
        return False
    return True


def _try_acquire_fd(fd: int) -> bool:
    if sys.platform == "win32":
        return _try_acquire_fd_win32(fd)  # pragma: no cover
    return _try_acquire_fd_unix(fd)  # pragma: no cover


def _release_fd_win32(fd: int) -> None:  # pragma: no cover
    import msvcrt

    try:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined, misc]
    except OSError:
        pass


def _release_fd_unix(fd: int) -> None:  # pragma: no cover
    import fcntl

    with suppress(OSError):
        fcntl.flock(fd, fcntl.LOCK_UN)  # type: ignore[attr-defined, misc]


def _release_fd(fd: int) -> None:
    if sys.platform == "win32":
        _release_fd_win32(fd)  # pragma: no cover
    else:  # pragma: no cover
        _release_fd_unix(fd)


def _unknown_lock_info(wordlist: Path) -> OperationLockInfo:
    return OperationLockInfo(
        pid=0,
        started="unknown",
        command="unknown",
        wordlist=str(wordlist.resolve()),
    )


def read_active_operation_lock(wordlist: Path) -> OperationLockInfo | None:
    """Return lock metadata when the project flock is held.

    Ownership is the kernel lock, not PID metadata. After a successful push the
    lock file still names this process's PID; treating a live PID as an active
    lock falsely blocks the dashboard. Probe with a non-blocking flock instead.

    Unsafe or unreadable lock paths return a sentinel (not None) so the dashboard
    cannot report idle when mutation would refuse the lock.
    """
    lock_path = lock_path_for_wordlist(wordlist)
    root = trusted_project_root(wordlist)
    try:
        fd = open_trusted_regular_file(lock_path, root=root, create=False, mutable=True)
    except SecureArtifactError:
        if not lock_path.exists() and not lock_path.is_symlink():
            return None
        return OperationLockInfo(
            pid=0,
            started="unknown",
            command="unsafe-lock",
            wordlist=str(wordlist.resolve()),
        )
    except OSError:
        return OperationLockInfo(
            pid=0,
            started="unknown",
            command="unreadable-lock",
            wordlist=str(wordlist.resolve()),
        )
    try:
        if _try_acquire_fd(fd):
            # Flock free — ignore leftover / self PID metadata.
            _release_fd(fd)
            return None
        info = _read_lock_info_fd(fd)
        return info if info is not None else _unknown_lock_info(wordlist)
    finally:
        with suppress(OSError):  # pragma: no cover
            _close_lock_fd(fd)


def _close_lock_fd(fd: int) -> None:
    os.close(fd)


@contextmanager
def acquire_operation_lock(wordlist: Path, command: str) -> Iterator[OperationLockInfo]:
    """Acquire an exclusive project lock; release on exit.

    Invariant: if the kernel lock is not held, the lock file must not be unlinked
    or replaced. Metadata (PID) is diagnostics only — never ownership truth.
    """
    lock_path = lock_path_for_wordlist(wordlist)
    root = trusted_project_root(wordlist)
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OperationLockRejected(
            "could not create the project lock directory",
            code="lock_dir_unwritable",
        ) from exc
    info = OperationLockInfo(
        pid=os.getpid(),
        started=datetime.now(UTC).replace(microsecond=0).isoformat(),
        command=command,
        wordlist=str(wordlist.resolve()),
    )

    try:
        fd = open_trusted_regular_file(lock_path, root=root, create=True, mutable=True)
    except SecureArtifactError as exc:
        raise OperationLockRejected(exc.detail, code=exc.code) from exc
    try:
        if not _try_acquire_fd(fd):
            existing = _read_lock_info_fd(fd)
            raise OperationLocked(
                existing if existing is not None else _unknown_lock_info(wordlist),
                lock_path,
            )
        # We hold the kernel lock — overwrite stale metadata unconditionally.
        _write_lock_info(fd, info)
        try:
            yield info
        finally:
            _release_fd(fd)
    finally:
        with suppress(OSError):  # pragma: no cover -- rare fd close failure; exercised on Unix CI
            _close_lock_fd(fd)
