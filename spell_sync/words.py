"""Word normalization and classification."""

from __future__ import annotations

import re
from typing import Iterable, Set

WordSet = Set[str]

# --- Regular expressions ---

_RE_CYRILLIC = re.compile(r"[А-Яа-яЁё]")
_RE_LATIN = re.compile(r"[A-Za-z]")


# --- Classification ---


def has_cyrillic(word: str) -> bool:
    return bool(_RE_CYRILLIC.search(word))


def has_latin(word: str) -> bool:
    return bool(_RE_LATIN.search(word))


def subset_russian(words: WordSet) -> WordSet:
    """Cyrillic and everything without Latin (symbols, Greek, digits)."""
    return {w for w in words if has_cyrillic(w) or not has_latin(w)}


def subset_english(words: WordSet) -> WordSet:
    return {w for w in words if has_latin(w)}


# --- Normalization ---


def normalize_token(word: str | None) -> str:
    if word is None:
        return ""
    return word.strip().lstrip("\ufeff")


def is_hard_junk(word: str) -> bool:
    """Junk: empty, whitespace, control characters, punctuation only."""
    if not word:
        return True
    if any(ch.isspace() for ch in word):
        return True
    if any(ord(ch) < 32 for ch in word):
        return True
    if all(not ch.isalnum() for ch in word):
        return True
    return False


def clean_words(words: Iterable[str | None]) -> WordSet:
    result: WordSet = set()
    for word in words:
        normalized = normalize_token(word)
        if normalized and not is_hard_junk(normalized):
            result.add(normalized)
    return result


def sort_words(words: Iterable[str | None]) -> list[str]:
    return sorted(clean_words(words), key=str.casefold)


def merge_case_duplicates(words: Iterable[str | None]) -> list[str]:
    """Keep first seen spelling per case-insensitive key."""
    canonical: dict[str, str] = {}
    for word in words:
        normalized = normalize_token(word)
        if not normalized or is_hard_junk(normalized):
            continue
        key = normalized.casefold()
        if key not in canonical:
            canonical[key] = normalized
    return sort_words(canonical.values())
