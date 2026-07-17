"""Immutable push plan: one parse per target, shared by guards and writes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .dictionaries import Dictionary
from .exit_codes import ExitCode
from .log import log
from .push_render import RenderedWrite
from .read_outcome import (
    DictionaryReadResult,
    ReadStatus,
    dictionary_read_result,
    fingerprint_matches,
    is_readable_for_push,
)
from .words import WordSet

if TYPE_CHECKING:
    from .sync_context import RuntimeContext


@dataclass(frozen=True)
class PlannedTarget:
    """One dictionary target with a single full-file read result."""

    dictionary: Dictionary
    read_result: DictionaryReadResult
    target_words: frozenset[str]
    additions: frozenset[str]
    removals: frozenset[str]
    rendered: RenderedWrite | None = None


@dataclass(frozen=True)
class PushPlan:
    """Frozen push plan consumed by dry-run, backups, guards, and writes."""

    words: WordSet
    targets: tuple[PlannedTarget, ...]
    skipped_unreadable: tuple[str, ...]
    skipped_corrupt: tuple[str, ...]
    skipped_blocked: tuple[str, ...]


def _plan_one(
    dictionary: Dictionary,
    wordlist_words: WordSet,
    *,
    local_words: frozenset[str],
    read_result: DictionaryReadResult,
) -> PlannedTarget:
    target = frozenset(dictionary.target_words(wordlist_words))
    return PlannedTarget(
        dictionary=dictionary,
        read_result=read_result,
        target_words=target,
        additions=target - local_words,
        removals=local_words - target,
    )


def build_push_plan(
    ctx: RuntimeContext,
    words: WordSet,
    *,
    skip_names: frozenset[str] | None = None,
) -> PushPlan | ExitCode:
    """Parse each dictionary once and assemble an immutable push plan."""
    if not words:
        log.abort("wordlist is empty — push aborted.")
        return ExitCode.PUSH_ABORT

    blocked = skip_names or frozenset()
    skipped_unreadable: list[str] = []
    skipped_corrupt: list[str] = []
    skipped_blocked: list[str] = []
    planned: list[PlannedTarget] = []

    for dictionary in ctx.dictionaries:
        if dictionary.name in blocked:
            skipped_blocked.append(dictionary.name)
            continue
        read_result = dictionary_read_result(dictionary)
        status = read_result.status
        if status is ReadStatus.UNREADABLE:
            skipped_unreadable.append(dictionary.name)
            continue
        if status in (ReadStatus.CORRUPT, ReadStatus.UNSUPPORTED):
            skipped_corrupt.append(dictionary.name)
            continue
        if not is_readable_for_push(status):
            continue  # pragma: no cover -- defensive
        local_words = read_result.words
        planned.append(
            _plan_one(
                dictionary,
                words,
                local_words=local_words,
                read_result=read_result,
            )
        )

    return PushPlan(
        words=words,
        targets=tuple(planned),
        skipped_unreadable=tuple(skipped_unreadable),
        skipped_corrupt=tuple(skipped_corrupt),
        skipped_blocked=tuple(skipped_blocked),
    )


def max_local_word_count(plan: PushPlan) -> int:
    """Largest local dictionary size from a frozen push plan."""
    return max((len(t.read_result.words) for t in plan.targets), default=0)


def max_removals_in_plan(plan: PushPlan) -> int:
    return max((len(t.removals) for t in plan.targets), default=0)


def fingerprint_conflict(dictionary: Dictionary, read_result: DictionaryReadResult) -> bool:
    """True when on-disk content no longer matches the plan parse fingerprint."""
    if read_result.fingerprint is None:
        return False
    return not fingerprint_matches(Path(dictionary.path), read_result.fingerprint)
