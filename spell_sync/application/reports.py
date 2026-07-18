"""Structured application results shared by CLI and TUI."""

from __future__ import annotations

from dataclasses import dataclass

from ..exit_codes import ExitCode
from ..push_prepared import PreparedPush
from ..sync_models import DictionaryDiff, PushResult


@dataclass(frozen=True)
class StatusSnapshot:
    wordlist_count: int
    diffs: tuple[DictionaryDiff, ...]
    skipped_unreadable: tuple[str, ...]
    skipped_corrupt: tuple[str, ...]
    wordlist_error: ExitCode | None = None
    destructive_risk: str | None = None
    empty_wordlist: bool = False


@dataclass(frozen=True)
class PushExecution:
    """Outcome of push prepare/execute using one PreparedPush instance."""

    prepared: PreparedPush
    result: PushResult | ExitCode
