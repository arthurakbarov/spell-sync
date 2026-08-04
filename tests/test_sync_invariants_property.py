"""Property tests for Pull union and Push subset invariants."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from spell_sync.words import (
    clean_words,
    has_latin,
    merge_case_duplicates,
    subset_english,
    subset_russian,
    union_words_casefold,
)

_WORD_ATOMS = (
    "alpha",
    "Alpha",
    "ALPHA",
    "beta",
    "os",
    "OS",
    "слово",
    "Слово",
    "прокcи",
    "backend",
    "1080p",
    "π",
    "миксMix",
)

_word_lists = st.lists(st.sampled_from(_WORD_ATOMS), max_size=12)
_word_sets = st.frozensets(st.sampled_from(_WORD_ATOMS), max_size=12)


def _casefold_set(words: list[str] | set[str]) -> set[str]:
    return {word.casefold() for word in words}


@given(words=_word_lists)
@settings(max_examples=80, deadline=None)
def test_clean_words_idempotent(words: list[str]) -> None:
    once = clean_words(words)
    assert clean_words(once) == once


@given(words=_word_lists)
@settings(max_examples=80, deadline=None)
def test_merge_case_duplicates_unique_keys(words: list[str]) -> None:
    merged = merge_case_duplicates(words)
    keys = [word.casefold() for word in merged]
    assert len(keys) == len(set(keys))
    assert _casefold_set(merged) == _casefold_set(clean_words(words))


@given(base=_word_lists, extra=_word_lists)
@settings(max_examples=80, deadline=None)
def test_pull_union_absorbs_and_commutes_membership(base: list[str], extra: list[str]) -> None:
    once = union_words_casefold(base, extra)
    twice = union_words_casefold(once, extra)
    assert once == twice
    assert _casefold_set(once) == _casefold_set(clean_words(base)) | _casefold_set(
        clean_words(extra)
    )
    left = _casefold_set(union_words_casefold(base, extra))
    right = _casefold_set(union_words_casefold(extra, base))
    assert left == right


@given(words=_word_sets)
@settings(max_examples=80, deadline=None)
def test_push_subsets_are_idempotent_and_disjoint_for_pure_latin(words: frozenset[str]) -> None:
    eng = subset_english(set(words))
    rus = subset_russian(set(words))
    assert subset_english(eng) == eng
    assert subset_russian(rus) == rus
    pure_latin = {word for word in words if has_latin(word) and word.isascii()}
    assert pure_latin <= eng
    assert pure_latin.isdisjoint(rus)
