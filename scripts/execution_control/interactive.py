"""Interactive prompt accounting outside execution budgets."""

from __future__ import annotations

import sys
import threading
import time
from contextlib import contextmanager
from typing import Iterator, TextIO

from .eta import PROMPT_ALLOWANCE_SECONDS
from .session import record_session_event

_local = threading.local()


def _bucket() -> list[float]:
    bucket = getattr(_local, "waiting_seconds", None)
    if bucket is None:
        bucket = []
        _local.waiting_seconds = bucket
    return bucket


def current_waiting_seconds() -> float:
    return float(sum(_bucket()))


def add_waiting_seconds(seconds: float) -> None:
    if seconds > 0:
        _bucket().append(float(seconds))


@contextmanager
def capture_waiting() -> Iterator[list[float]]:
    """Accumulate interactive waits in this scope; restore prior bucket on exit."""
    prior = getattr(_local, "waiting_seconds", None)
    bucket: list[float] = []
    _local.waiting_seconds = bucket
    try:
        yield bucket
    finally:
        if prior is None:
            if hasattr(_local, "waiting_seconds"):
                delattr(_local, "waiting_seconds")
        else:
            _local.waiting_seconds = prior


def prompt_user(
    message: str,
    *,
    stream_in: TextIO | None = None,
    stream_out: TextIO | None = None,
) -> str:
    """Read one user reply; measure wait and keep it out of work-budget accounting."""
    out = stream_out if stream_out is not None else sys.stderr
    inp = stream_in if stream_in is not None else sys.stdin
    out.write(message)
    if message and not message.endswith((" ", "\n", "\t")):
        out.write(" ")
    out.flush()
    started = time.monotonic()
    line = inp.readline()
    waited = max(0.0, time.monotonic() - started)
    add_waiting_seconds(waited)
    record_session_event(category="waiting", duration_seconds=waited)
    return line.rstrip("\n")


def interactive_allowance_seconds(prompt_count: int) -> float:
    return max(0, int(prompt_count)) * PROMPT_ALLOWANCE_SECONDS
