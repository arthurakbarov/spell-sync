"""Word normalization and classification."""

import re
import unicodedata
from collections.abc import Iterable

type WordSet = set[str]

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
    # NFC so composed/decomposed Unicode spellings share one casefold key.
    return unicodedata.normalize("NFC", word.strip().lstrip("\ufeff"))


def is_hard_junk(word: str) -> bool:
    """Junk: empty, whitespace, control characters, punctuation only."""
    if not word:
        return True
    if any(ch.isspace() for ch in word):
        return True
    if any(ord(ch) < 32 for ch in word):
        return True
    return all(not ch.isalnum() for ch in word)


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


def added_words_casefold(
    existing: Iterable[str],
    incoming: Iterable[str | None],
) -> list[str]:
    """Words from ``incoming`` whose casefold key is not already in ``existing``.

    Incoming words are cleaned and sorted first. First spelling for a new
    casefold key wins. Used by Pull merge so preview and add-from share one
    algorithm.
    """
    seen = {word.casefold() for word in existing}
    added: list[str] = []
    for word in sort_words(incoming):
        key = word.casefold()
        if key not in seen:
            added.append(word)
            seen.add(key)
    return added


def union_words_casefold(*groups: Iterable[str | None]) -> list[str]:
    """Case-insensitive union of word groups (Pull merge).

    Within each group, words are cleaned and sorted. Across groups, the first
    spelling for a casefold key wins. The result is then
    :func:`merge_case_duplicates`-normalized.
    """
    ordered: list[str] = []
    for group in groups:
        ordered.extend(added_words_casefold(ordered, group))
    return merge_case_duplicates(ordered)
