"""Unified human-mode CLI operation presentation.

Intro → optional ETA (≥5s) → indented progress / hang heartbeats → outcome.
"""

import math
import threading
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal

from .log import Log
from .log import log as default_log
from .operation_lifecycle import emit_operation_finished, emit_operation_started
from .operation_timing import eta_line, hang_threshold_seconds, record_sample

_OutcomeKind = Literal["done", "warn", "error", "abort"]


@dataclass(frozen=True, slots=True)
class OperationSpec:
    """Identity and intro copy for one user-facing CLI operation."""

    key: str
    title: str
    descriptions: tuple[str, ...] = ()
    # Short product-language name for hang heartbeats (not the internal key).
    activity: str = ""


class OperationSession:
    """Active CLI operation: EventSink + hang watchdog + outcome."""

    def __init__(
        self,
        spec: OperationSpec,
        *,
        log: Log,
        record_timing: bool,
    ) -> None:
        self.spec = spec
        self._log = log
        self._record_timing = record_timing
        self._started = time.monotonic()
        self._last_progress = self._started
        self._lock = threading.Lock()
        self._closed = False
        self._finished = False
        self._seen_messages: set[str] = set()
        self._stop_hang = threading.Event()
        self._hang_thread: threading.Thread | None = None

    @property
    def elapsed_ms(self) -> int:
        return max(0, round((time.monotonic() - self._started) * 1000))

    def start(self) -> None:
        emit_operation_started(self.spec.key)
        self._log.section(self.spec.title)
        for line in self.spec.descriptions:
            self._log.info(line)
        hint = eta_line(self.spec.key)
        if hint is not None:
            self._log.info(hint)
        self._start_hang_watch()

    def __call__(self, event: object) -> None:
        """Presentation EventSink for SpellSyncService.execute_*."""
        message = str(getattr(event, "message", "") or "").strip()
        if not message:
            return
        severity = getattr(event, "severity", None)
        severity_value = str(getattr(severity, "value", severity) or "").lower()
        # Terminal lifecycle lines are owned by succeed/fail to avoid duplicates.
        if severity_value in {"success", "error"}:
            self._touch()
            return
        with self._lock:
            if message in self._seen_messages:
                self._touch_unlocked()
                return
            self._seen_messages.add(message)
            self._touch_unlocked()
        if severity_value == "warning":
            self._log.warn(message)
        else:
            self._log.detail(f"· {message}")

    def note(self, message: str) -> None:
        text = message.strip()
        if not text:
            return
        self._touch()
        self._log.detail(f"· {text}")

    def succeed(self, message: str, *, details: Sequence[str] = ()) -> None:
        self._finish("done", message, details=details, record=True)

    def warn_outcome(self, message: str, *, details: Sequence[str] = ()) -> None:
        self._finish("warn", message, details=details, record=True)

    def fail(self, message: str, *, details: Sequence[str] = ()) -> None:
        self._finish("error", message, details=details, record=False)

    def abort(self, message: str, *, details: Sequence[str] = ()) -> None:
        self._finish("abort", message, details=details, record=False)

    def close(self) -> None:
        """Stop heartbeats without printing an outcome (caller already finished)."""
        if self._closed:
            return
        self._closed = True
        self._stop_hang.set()
        thread = self._hang_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=0.2)

    def _finish(
        self,
        kind: _OutcomeKind,
        message: str,
        *,
        details: Sequence[str],
        record: bool,
    ) -> None:
        if self._finished:
            return
        self._finished = True
        self.close()
        if kind == "done":
            self._log.done(message)
        elif kind == "warn":
            self._log.warn(message)
        elif kind == "abort":
            self._log.abort(message)
        else:
            self._log.error(message)
        for line in details:
            self._log.detail(line)
        emit_operation_finished(self.spec.key, kind=kind)
        if record and self._record_timing and not self._log.quiet:
            elapsed = time.monotonic() - self._started
            record_sample(self.spec.key, elapsed)

    def _touch(self) -> None:
        with self._lock:
            self._touch_unlocked()

    def _touch_unlocked(self) -> None:
        self._last_progress = time.monotonic()

    def _start_hang_watch(self) -> None:
        threshold = hang_threshold_seconds(self.spec.key)
        if not math.isfinite(threshold):
            return

        def _watch() -> None:
            while not self._stop_hang.wait(2.0):
                with self._lock:
                    silent = time.monotonic() - self._last_progress
                if silent >= threshold:
                    label = (self.spec.activity or self.spec.title or self.spec.key).strip()
                    self._log.info(f"Still working on {label}...")
                    self._touch()

        self._hang_thread = threading.Thread(
            target=_watch,
            name=f"spell-sync-hang-{self.spec.key}",
            daemon=True,
        )
        self._hang_thread.start()


@contextmanager
def operation_session(
    spec: OperationSpec,
    *,
    enabled: bool = True,
    log: Log | None = None,
    record_timing: bool = True,
) -> Iterator[OperationSession | None]:
    """Run a human-mode operation session; yields None when disabled (JSON/quiet)."""
    active_log = log if log is not None else default_log
    if not enabled or active_log.quiet:
        yield None
        return
    session = OperationSession(spec, log=active_log, record_timing=record_timing)
    session.start()
    try:
        yield session
    finally:
        session.close()
