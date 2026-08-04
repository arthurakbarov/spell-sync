"""JSONL operation history storage."""

from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from typing import Iterator

from ..operation_reports import OperationOutcome
from .history_record import OperationHistoryRecord
from .path_guard import (
    PathCheckResult,
    open_append_only,
    safe_unlink,
    validate_directory_path,
    validate_file_path,
)
from .paths import AppStatePaths
from .technical_event_model import OperationKind
from .types import HistoryClearResult, HistoryReadResult, HistoryWriteResult

MAX_HISTORY_RECORDS = 500


def _try_acquire_fd(fd: int, *, blocking: bool = False) -> bool:
    if sys.platform == "win32":  # pragma: no cover
        import msvcrt

        mode = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, mode, 1)  # type: ignore[attr-defined]
        except OSError:
            return False
        return True
    import fcntl

    flags = fcntl.LOCK_EX if blocking else (fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        fcntl.flock(fd, flags)  # type: ignore[attr-defined]
    except BlockingIOError:
        return False
    return True


def _release_fd(fd: int) -> None:
    if sys.platform == "win32":  # pragma: no cover
        import msvcrt

        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
        except OSError:
            pass
        return
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_UN)  # type: ignore[attr-defined]
    except OSError:
        pass


class OperationHistoryStore:
    def __init__(self, paths: AppStatePaths) -> None:
        self._paths = paths
        self._session_record_ids: set[str] = set()

    @property
    def paths(self) -> AppStatePaths:
        return self._paths

    def _ensure_state_dir(self) -> PathCheckResult:
        check = validate_directory_path(
            self._paths.state_directory,
            root=self._paths.state_directory,
        )
        if not check.ok:
            return check
        try:
            self._paths.state_directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return PathCheckResult(False, str(exc))
        return PathCheckResult(True)

    @contextmanager
    def _history_lock(self) -> Iterator[bool]:
        dir_check = self._ensure_state_dir()
        if not dir_check.ok:
            yield False
            return
        lock_check = validate_file_path(
            self._paths.history_lock,
            root=self._paths.state_directory,
        )
        if not lock_check.ok:
            yield False
            return
        fd = os.open(self._paths.history_lock, os.O_CREAT | os.O_RDWR, 0o600)
        acquired = False
        try:
            acquired = _try_acquire_fd(fd, blocking=True)
            yield acquired
        finally:
            if acquired:
                _release_fd(fd)
            try:
                os.close(fd)
            except OSError:
                pass

    def append(self, record: OperationHistoryRecord) -> HistoryWriteResult:
        if record.record_id in self._session_record_ids:
            return HistoryWriteResult(ok=True, record_id=record.record_id, duplicate=True)
        with self._history_lock() as acquired:
            if not acquired:
                return HistoryWriteResult(ok=False, detail="History lock unavailable.")
            existing_ids = self._read_record_ids_unlocked()
            if record.record_id in existing_ids:
                self._session_record_ids.add(record.record_id)
                return HistoryWriteResult(ok=True, record_id=record.record_id, duplicate=True)
            line = json.dumps(record.to_json_dict(), ensure_ascii=False, sort_keys=True)
            fd, open_error = open_append_only(
                self._paths.history_file,
                root=self._paths.state_directory,
            )
            if open_error is not None:
                return HistoryWriteResult(ok=False, detail=open_error)
            assert fd is not None
            try:
                payload = (line + "\n").encode("utf-8")
                os.write(fd, payload)
            except OSError as exc:
                return HistoryWriteResult(ok=False, detail=str(exc))
            finally:
                try:
                    os.close(fd)
                except OSError:
                    pass
            self._session_record_ids.add(record.record_id)
            self._maybe_compact_unlocked()
            return HistoryWriteResult(ok=True, record_id=record.record_id)

    def _read_record_ids_unlocked(self) -> set[str]:
        if not self._paths.history_file.is_file():
            return set()
        ids: set[str] = set()
        try:
            text = self._paths.history_file.read_text(encoding="utf-8")
        except OSError:
            return set()
        for line in text.splitlines():
            record = self._parse_line(line)
            if record is not None:
                ids.add(record.record_id)
        return ids

    def _parse_line(self, line: str) -> OperationHistoryRecord | None:
        stripped = line.strip()
        if not stripped:
            return None
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        return OperationHistoryRecord.from_json_dict(data)

    def read_recent(
        self,
        *,
        limit: int = 50,
        operation: OperationKind | None = None,
        outcome: OperationOutcome | None = None,
    ) -> HistoryReadResult:
        bounded = max(1, min(limit, 500))
        read_check = validate_file_path(
            self._paths.history_file,
            root=self._paths.state_directory,
        )
        if not read_check.ok and self._paths.history_file.exists():
            return HistoryReadResult(records=(), detail=read_check.detail)
        if not self._paths.history_file.is_file():
            return HistoryReadResult(records=())
        malformed = 0
        records: list[OperationHistoryRecord] = []
        try:
            lines = self._paths.history_file.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            return HistoryReadResult(records=(), detail=str(exc))
        for line in lines:
            parsed = self._parse_line(line)
            if parsed is None and line.strip():
                malformed += 1
                continue
            if parsed is not None:
                records.append(parsed)
        filtered: list[OperationHistoryRecord] = []
        for record in reversed(records):
            if operation is not None and record.operation != operation.value:
                continue
            if outcome is not None and record.outcome != outcome.value:
                continue
            filtered.append(record)
            if len(filtered) >= bounded:
                break
        return HistoryReadResult(tuple(filtered), malformed_lines=malformed)

    def clear(self) -> HistoryClearResult:
        with self._history_lock() as acquired:
            if not acquired:
                return HistoryClearResult(ok=False, detail="History lock unavailable.")
            unlink = safe_unlink(
                self._paths.history_file,
                root=self._paths.state_directory,
            )
            if not unlink.ok:
                return HistoryClearResult(ok=False, detail=unlink.detail)
            self._session_record_ids.clear()
            return HistoryClearResult(ok=True)

    def _maybe_compact_unlocked(self) -> None:
        if not self._paths.history_file.is_file():
            return
        try:
            lines = self._paths.history_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        parsed: list[OperationHistoryRecord] = []
        for line in lines:
            record = self._parse_line(line)
            if record is not None:
                parsed.append(record)
        if len(parsed) <= MAX_HISTORY_RECORDS:
            return
        kept = parsed[-MAX_HISTORY_RECORDS:]
        temp_path = self._paths.history_file.with_suffix(".jsonl.tmp")
        temp_check = validate_file_path(temp_path, root=self._paths.state_directory)
        if not temp_check.ok:
            return
        payload = "\n".join(
            json.dumps(record.to_json_dict(), ensure_ascii=False, sort_keys=True) for record in kept
        )
        if payload:
            payload += "\n"
        try:
            temp_path.write_text(payload, encoding="utf-8")
            temp_path.replace(self._paths.history_file)
        except OSError:
            if temp_path.is_file():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
