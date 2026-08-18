"""Append guest-entered words to the personal word list."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..guest_messages import (
    WORD_LIST_NOT_FOUND,
    WORD_LIST_UNREADABLE,
    WORD_LIST_WRITE_FAILED,
    already_present_detail,
    skipped_words_detail,
)
from ..io import read_text_words, wordlist_unreadable, write_text_words
from ..words import WordSet, clean_words, sort_words
from .mutation_scope import mutation_scope_for


@dataclass(frozen=True, slots=True)
class AppendWordsResult:
    """Outcome of merging typed words into wordlist.txt."""

    path: Path
    added: tuple[str, ...]
    already_present: tuple[str, ...]
    rejected: tuple[str, ...]

    @property
    def added_count(self) -> int:
        return len(self.added)

    @property
    def accepted_keys(self) -> frozenset[str]:
        """Casefold keys that are in the list after this append (added or already present)."""
        return frozenset(word.casefold() for word in (*self.added, *self.already_present))

    @property
    def had_usable_input(self) -> bool:
        """True when at least one token was accepted (new or already present)."""
        return bool(self.accepted_keys)

    def detail_lines(self) -> tuple[str, ...]:
        lines: list[str] = []
        if self.already_present:
            lines.append(already_present_detail(self.already_present))
        if self.rejected:
            lines.append(skipped_words_detail(self.rejected))
        return tuple(lines)


def parse_word_lines(raw: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split textarea input into cleaned words and rejected raw tokens."""
    accepted: list[str] = []
    rejected: list[str] = []
    seen: set[str] = set()
    for line in raw.splitlines():
        token = line.strip()
        if not token:
            continue
        cleaned = clean_words([token])
        if not cleaned:
            rejected.append(token)
            continue
        word = next(iter(cleaned))
        key = word.casefold()
        if key in seen:
            continue
        seen.add(key)
        accepted.append(word)
    return tuple(sort_words(accepted)), tuple(rejected)


def _load_existing_words(path: Path) -> WordSet:
    """Load wordlist words, failing closed on unreadable or undecodable files."""
    if wordlist_unreadable(path):
        raise OSError(WORD_LIST_UNREADABLE)
    return clean_words(read_text_words(str(path), quiet=True))


def append_words_to_wordlist(path: Path, raw: str) -> AppendWordsResult:
    """Merge typed words into an existing wordlist.txt (additive, sorted)."""
    if not path.is_file():
        raise FileNotFoundError(WORD_LIST_NOT_FOUND)
    accepted, rejected = parse_word_lines(raw)
    existing = _load_existing_words(path)
    existing_keys = {w.casefold() for w in existing}
    added: list[str] = []
    already: list[str] = []
    for word in accepted:
        if word.casefold() in existing_keys:
            already.append(word)
            continue
        existing.add(word)
        existing_keys.add(word.casefold())
        added.append(word)
    if added and not write_text_words(str(path), existing, "utf-8", False, quiet=True):
        raise OSError(WORD_LIST_WRITE_FAILED)
    return AppendWordsResult(
        path=path,
        added=tuple(sort_words(added)),
        already_present=tuple(sort_words(already)),
        rejected=rejected,
    )


def append_words_guarded(
    path: Path,
    raw: str,
    *,
    json_output: bool = False,
) -> AppendWordsResult | int:
    """Lock + config/journal guards, then append words (shared CLI/TUI path)."""
    with mutation_scope_for(path, "add", json_output=json_output) as scope:
        if isinstance(scope, int):
            return scope
        return append_words_to_wordlist(path, raw)
