"""Shared result types for pull, push, and status."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PushResult:
    """Successful push result: words and which dictionaries were written / skipped."""

    word_count: int
    written: tuple[str, ...]
    skipped: tuple[str, ...] = ()
    skipped_reasons: dict[str, str] = field(default_factory=dict)
    skipped_details: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DictionaryDiff:
    """Diff between wordlist (target) and a local dictionary."""

    name: str
    target_count: int
    local_count: int
    to_add: int
    to_remove: int
    add_words: tuple[str, ...] = ()
    remove_words: tuple[str, ...] = ()
