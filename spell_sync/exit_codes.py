"""CLI exit codes."""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    OK = 0
    PUSH_ABORT = 1
    LINT_FAILED = 2
    UNKNOWN_COMMAND = 3
    CANCELLED = 4
    PARTIAL_PUSH = 5
    WORDLIST_UNREADABLE = 6
    SYNC_INTERRUPTED = 130
