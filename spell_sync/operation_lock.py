"""Cross-platform project lock for mutating spell-sync operations."""

from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .project import ProjectContext


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


def _pid_alive_win32(pid: int) -> bool:  # pragma: no cover
    import ctypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)  # type: ignore[attr-defined]
    if handle:
        ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
        return True
    return False


def _pid_alive_unix(pid: int) -> bool:  # pragma: no cover
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    else:
        return True


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        return _pid_alive_win32(pid)  # pragma: no cover
    return _pid_alive_unix(pid)  # pragma: no cover


def _read_lock_info(path: Path) -> OperationLockInfo | None:
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return OperationLockInfo(
            pid=int(data["pid"]),
            started=str(data["started"]),
            command=str(data["command"]),
            wordlist=str(data["wordlist"]),
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
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

    try:
        fcntl.flock(fd, fcntl.LOCK_UN)  # type: ignore[attr-defined, misc]
    except OSError:
        pass


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


@contextmanager
def acquire_operation_lock(wordlist: Path, command: str) -> Iterator[OperationLockInfo]:
    """Acquire an exclusive project lock; release on exit.

    Invariant: if the kernel lock is not held, the lock file must not be unlinked
    or replaced. Metadata (PID) is diagnostics only — never ownership truth.
    """
    lock_path = lock_path_for_wordlist(wordlist)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    info = OperationLockInfo(
        pid=os.getpid(),
        started=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        command=command,
        wordlist=str(wordlist.resolve()),
    )

    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if not _try_acquire_fd(fd):
            existing = _read_lock_info(lock_path)
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
        try:
            os.close(fd)
        except OSError:  # pragma: no cover -- rare fd close failure; exercised on Unix CI
            pass
