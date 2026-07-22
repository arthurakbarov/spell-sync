"""Owned process-group execution and termination."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .progress import ProgressTracker


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


def _read_stream(
    stream, tracker: ProgressTracker | None, sink: list[str], limit: int = 200
) -> None:
    try:
        for raw in iter(stream.readline, b""):
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace")
            sink.append(line)
            if len(sink) > limit:
                sink.pop(0)
            if tracker is not None:
                tracker.observe_line(line)
    finally:
        stream.close()


def _terminate_owned_group(
    pgid: int, *, grace: float, proc: subprocess.Popen[bytes] | None = None
) -> None:
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError:
        if proc is not None:
            proc.terminate()
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            return
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return
        except PermissionError:
            if proc is not None and proc.poll() is not None:
                return
        time.sleep(0.05)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except PermissionError:
        if proc is not None:
            proc.kill()
        return


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
) -> ProcessResult:
    started = time.monotonic()
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
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
    stdout_thread = threading.Thread(
        target=_read_stream,
        args=(proc.stdout, tracker, stdout_lines),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_read_stream,
        args=(proc.stderr, tracker, stderr_lines),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    timed_out = False
    timeout_kind: str | None = None
    exit_code = 1

    while True:
        now = time.monotonic()
        elapsed = now - started
        if proc.poll() is not None:
            exit_code = proc.returncode if proc.returncode is not None else 1
            break
        if enforce_hard and elapsed >= hard_seconds:
            timed_out = True
            timeout_kind = "hard"
            _terminate_owned_group(pgid, grace=termination_grace_seconds, proc=proc)
            proc.wait(timeout=termination_grace_seconds + 1)
            exit_code = 124
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
            _terminate_owned_group(pgid, grace=termination_grace_seconds, proc=proc)
            proc.wait(timeout=termination_grace_seconds + 1)
            exit_code = 124
            break
        time.sleep(0.05)

    stdout_thread.join(timeout=1)
    stderr_thread.join(timeout=1)
    duration = time.monotonic() - started
    return ProcessResult(
        exit_code=exit_code,
        duration_seconds=duration,
        timed_out=timed_out,
        timeout_kind=timeout_kind,
        stdout_tail="".join(stdout_lines[-50:]),
        stderr_tail="".join(stderr_lines[-50:]),
        progress_event_count=tracker.event_count if tracker else 0,
        maximum_progress_gap=tracker.maximum_gap if tracker else 0.0,
    )
