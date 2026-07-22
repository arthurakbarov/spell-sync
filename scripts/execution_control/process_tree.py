"""Owned process-group execution, descendant cleanup, and termination."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .progress import ProgressTracker
from .reporting import print_soft_overrun


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class ProcessIdentity:
    pid: int
    start_marker: str
    state: str

    def is_running(self) -> bool:
        if self.state.startswith("Z"):
            return False
        current = read_process_identity(self.pid)
        if current is None:
            return False
        if current.state.startswith("Z"):
            return False
        return current.start_marker == self.start_marker and current.pid == self.pid


@dataclass(frozen=True, slots=True)
class OwnershipSnapshot:
    root_pid: int
    owned_pgid: int
    identities: tuple[ProcessIdentity, ...]


@dataclass(frozen=True, slots=True)
class ProcessResult:
    exit_code: int
    duration_seconds: float
    timed_out: bool
    timeout_kind: str | None
    stdout_tail: str
    stderr_tail: str
    progress_event_count: int
    maximum_progress_gap: float
    start_time_iso: str
    end_time_iso: str
    interrupted: bool = False
    owned_pgid: int | None = None
    owned_root_pid: int | None = None
    detached_pids: tuple[int, ...] = ()


def _process_group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _collect_ppid_map() -> dict[int, int]:
    mapping: dict[int, int] = {}
    for argv in (
        ["ps", "-ax", "-o", "pid=", "-o", "ppid="],
        ["ps", "-eo", "pid", "ppid"],
        ["ps", "-e", "-o", "pid", "ppid"],
    ):
        try:
            output = subprocess.check_output(argv, text=True, timeout=1.0)
        except (subprocess.SubprocessError, OSError):
            continue
        for line in output.splitlines():
            parts = line.strip().split()
            if len(parts) != 2:
                continue
            try:
                mapping[int(parts[0])] = int(parts[1])
            except ValueError:
                continue
        if mapping:
            break
    return mapping


def read_process_identity(pid: int) -> ProcessIdentity | None:
    if pid <= 0:
        return None
    for argv in (
        ["ps", "-p", str(pid), "-o", "state=", "-o", "lstart="],
        ["ps", "-p", str(pid), "-o", "stat=", "-o", "lstart="],
    ):
        try:
            output = subprocess.check_output(argv, text=True, timeout=0.5).strip()
        except (subprocess.SubprocessError, OSError):
            continue
        parts = output.split(maxsplit=1)
        if len(parts) != 2:
            continue
        state, start_marker = parts[0].strip(), parts[1].strip()
        if start_marker:
            return ProcessIdentity(pid=pid, start_marker=start_marker, state=state)
    return None


def collect_descendants(root_pid: int) -> set[int]:
    ppid_map = _collect_ppid_map()
    if not ppid_map:
        ident = read_process_identity(root_pid)
        return {root_pid} if ident is not None and ident.is_running() else set()
    descendants: set[int] = set()
    frontier = {root_pid}
    while frontier:
        current = frontier.pop()
        if current in descendants:
            continue
        descendants.add(current)
        for pid, ppid in ppid_map.items():
            if ppid == current and pid not in descendants:
                frontier.add(pid)
    return descendants


def capture_ownership_snapshot(root_pid: int, owned_pgid: int) -> OwnershipSnapshot:
    descendants = collect_descendants(root_pid)
    identities: list[ProcessIdentity] = []
    for pid in sorted(descendants):
        ident = read_process_identity(pid)
        if ident is not None:
            identities.append(ident)
    return OwnershipSnapshot(
        root_pid=root_pid,
        owned_pgid=owned_pgid,
        identities=tuple(identities),
    )


def _running_identities(identities: Iterable[ProcessIdentity]) -> list[ProcessIdentity]:
    return [ident for ident in identities if ident.is_running()]


def terminate_ownership_snapshot(
    snapshot: OwnershipSnapshot,
    *,
    grace: float,
) -> tuple[int, ...]:
    try:
        os.killpg(snapshot.owned_pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except PermissionError:
        pass
    for ident in snapshot.identities:
        if ident.pid == snapshot.root_pid:
            continue
        try:
            os.kill(ident.pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        except PermissionError:
            pass
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if not _running_identities(snapshot.identities):
            break
        time.sleep(0.05)
    if _process_group_exists(snapshot.owned_pgid):
        try:
            os.killpg(snapshot.owned_pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError:
            pass
    survivors = _running_identities(snapshot.identities)
    for ident in survivors:
        try:
            os.kill(ident.pid, signal.SIGKILL)
        except ProcessLookupError:
            continue
        except PermissionError:
            pass
    return tuple(ident.pid for ident in _running_identities(snapshot.identities))


def terminate_descendants(
    root_pid: int,
    *,
    grace: float,
    exclude: set[int] | None = None,
) -> tuple[int, ...]:
    exclude = exclude or set()
    snapshot = capture_ownership_snapshot(root_pid, root_pid)
    filtered = tuple(ident for ident in snapshot.identities if ident.pid not in exclude)
    return terminate_ownership_snapshot(
        OwnershipSnapshot(root_pid=root_pid, owned_pgid=root_pid, identities=filtered),
        grace=grace,
    )


def _terminate_owned_group(
    pgid: int,
    *,
    grace: float,
    root_pid: int | None = None,
    exclude: set[int] | None = None,
    snapshot: OwnershipSnapshot | None = None,
) -> tuple[int, ...]:
    del exclude
    if root_pid is not None:
        owned = snapshot or capture_ownership_snapshot(root_pid, pgid)
        return terminate_ownership_snapshot(owned, grace=grace)
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except PermissionError:
        pass
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if not _process_group_exists(pgid):
            break
        time.sleep(0.05)
    if _process_group_exists(pgid):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError:
            pass
    return tuple()


def _read_stream(
    stream,
    tracker: ProgressTracker | None,
    sink: list[str],
    *,
    limit: int = 200,
    live_writer: Callable[[str], None] | None = None,
) -> None:
    try:
        for raw in iter(stream.readline, b""):
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace")
            sink.append(line)
            if len(sink) > limit:
                sink.pop(0)
            if live_writer is not None:
                live_writer(line)
            if tracker is not None:
                tracker.observe_line(line)
    finally:
        stream.close()


def _join_reader_threads(*threads: threading.Thread, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    for thread in threads:
        remaining = max(0.0, deadline - time.monotonic())
        thread.join(timeout=remaining)


TickCallback = Callable[[float, ProgressTracker | None], None]


def run_owned_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None,
    hard_seconds: float,
    soft_seconds: float,
    stall_seconds: float | None,
    termination_grace_seconds: float,
    tracker: ProgressTracker | None,
    enforce_hard: bool = True,
    enforce_stall: bool = False,
    parent_deadline_monotonic: float | None = None,
    on_tick: TickCallback | None = None,
    soft_report_plan: object | None = None,
    active_child: str | None = None,
    stream_live: bool = False,
) -> ProcessResult:
    started_monotonic = time.monotonic()
    start_time_iso = _utc_now()
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    proc: subprocess.Popen[bytes] | None = None
    pgid: int | None = None
    root_pid: int | None = None
    stdout_thread: threading.Thread | None = None
    stderr_thread: threading.Thread | None = None
    timed_out = False
    timeout_kind: str | None = None
    exit_code = 1
    interrupted = False
    soft_reported = False
    last_status_report = started_monotonic
    detached_survivors: tuple[int, ...] = ()

    def _terminate_active_tree() -> tuple[int, ...]:
        if pgid is None or root_pid is None:
            return tuple()
        snapshot = capture_ownership_snapshot(root_pid, pgid)
        return terminate_ownership_snapshot(snapshot, grace=termination_grace_seconds)

    def _live_writer(line: str) -> None:
        if stream_live:
            sys.stdout.write(line)
            sys.stdout.flush()

    try:
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        assert proc.stdout is not None
        assert proc.stderr is not None
        pgid = proc.pid
        root_pid = proc.pid
        stdout_thread = threading.Thread(
            target=_read_stream,
            args=(proc.stdout, tracker, stdout_lines),
            kwargs={"live_writer": _live_writer if stream_live else None},
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_read_stream,
            args=(proc.stderr, tracker, stderr_lines),
            kwargs={"live_writer": _live_writer if stream_live else None},
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        while True:
            now = time.monotonic()
            elapsed = now - started_monotonic
            if proc.poll() is not None:
                exit_code = proc.returncode if proc.returncode is not None else 1
                break
            if parent_deadline_monotonic is not None and now >= parent_deadline_monotonic:
                timed_out = True
                timeout_kind = "hard"
                exit_code = 124
                detached_survivors = _terminate_active_tree()
                proc.wait(timeout=termination_grace_seconds + 1)
                break
            if enforce_hard and elapsed >= hard_seconds:
                timed_out = True
                timeout_kind = "hard"
                exit_code = 124
                detached_survivors = _terminate_active_tree()
                proc.wait(timeout=termination_grace_seconds + 1)
                break
            if (
                enforce_stall
                and stall_seconds is not None
                and tracker is not None
                and tracker.progress_age() >= stall_seconds
                and elapsed >= soft_seconds
            ):
                timed_out = True
                timeout_kind = "stall"
                detached_survivors = _terminate_active_tree()
                proc.wait(timeout=termination_grace_seconds + 1)
                exit_code = 124
                break
            if (
                soft_report_plan is not None
                and elapsed > soft_seconds
                and (not soft_reported or now - last_status_report >= 30.0)
            ):
                print_soft_overrun(
                    plan=soft_report_plan,
                    elapsed=elapsed,
                    active_child=active_child,
                    progress_age=tracker.progress_age() if tracker else 0.0,
                )
                soft_reported = True
                last_status_report = now
            if on_tick is not None:
                on_tick(elapsed, tracker)
            time.sleep(0.05)
    except KeyboardInterrupt:
        interrupted = True
        exit_code = 130
        detached_survivors = _terminate_active_tree()
        if proc is not None:
            try:
                proc.wait(timeout=termination_grace_seconds + 1)
            except subprocess.TimeoutExpired:
                detached_survivors = _terminate_active_tree()
        raise
    finally:
        if stdout_thread is not None and stderr_thread is not None:
            _join_reader_threads(stdout_thread, stderr_thread, timeout=1.0)
        elif stdout_thread is not None:
            stdout_thread.join(timeout=1.0)
        elif stderr_thread is not None:
            stderr_thread.join(timeout=1.0)
        if interrupted and pgid is not None and root_pid is not None:
            detached_survivors = _terminate_active_tree()

    duration = time.monotonic() - started_monotonic
    end_time_iso = _utc_now()
    return ProcessResult(
        exit_code=exit_code,
        duration_seconds=duration,
        timed_out=timed_out,
        timeout_kind=timeout_kind,
        stdout_tail="".join(stdout_lines[-50:]),
        stderr_tail="".join(stderr_lines[-50:]),
        progress_event_count=tracker.event_count if tracker else 0,
        maximum_progress_gap=tracker.maximum_gap if tracker else 0.0,
        start_time_iso=start_time_iso,
        end_time_iso=end_time_iso,
        interrupted=interrupted,
        owned_pgid=pgid,
        owned_root_pid=root_pid,
        detached_pids=detached_survivors,
    )
