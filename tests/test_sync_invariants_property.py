"""Property tests for Pull union and Push subset invariants."""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import read_text_words, write_text_words
from spell_sync.words import (
    clean_words,
    has_cyrillic,
    has_latin,
    merge_case_duplicates,
    subset_english,
    subset_russian,
    union_words_casefold,
)
from tests.runtime_helpers import make_sync_run

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


@given(a=_word_lists, b=_word_lists, c=_word_lists)
@settings(max_examples=60, deadline=None)
def test_pull_union_associates_membership(a: list[str], b: list[str], c: list[str]) -> None:
    left = _casefold_set(union_words_casefold(union_words_casefold(a, b), c))
    right = _casefold_set(union_words_casefold(a, union_words_casefold(b, c)))
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


@given(words=_word_sets)
@settings(max_examples=60, deadline=None)
def test_push_subset_filters_cover_cyrillic_and_latin(words: frozenset[str]) -> None:
    eng = subset_english(set(words))
    rus = subset_russian(set(words))
    for word in eng:
        assert has_latin(word)
    for word in rus:
        assert has_cyrillic(word) or not has_latin(word)
    assert eng | rus == set(words)


@given(base=_word_lists, dict_words=_word_lists)
@settings(max_examples=40, deadline=None)
def test_pull_push_pull_stabilizes_casefold_membership(
    base: list[str],
    dict_words: list[str],
) -> None:
    """Synthetic Pull → Push → Pull leaves casefold membership stable."""
    from hypothesis import assume

    assume(bool(clean_words(base)) or bool(clean_words(dict_words)))
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        wordlist = root / "wordlist.txt"
        dictionary = root / "dict.txt"
        write_text_words(wordlist, clean_words(base), "utf-8", False, quiet=True)
        write_text_words(dictionary, clean_words(dict_words), "utf-8", False, quiet=True)
        run = make_sync_run(
            wordlist,
            dictionaries=[Dictionary("synth", str(dictionary), DictionaryFormat.TEXT)],
        )

        pull1 = run.pull_into_wordlist()
        assert not isinstance(pull1, ExitCode), pull1
        after_pull1 = _casefold_set(read_text_words(wordlist, quiet=True))
        assume(bool(after_pull1))

        prepared = run.prepare_push_operation()
        assert not isinstance(prepared, ExitCode), prepared
        pushed = run.push_from_wordlist(prepared=prepared)
        assert not isinstance(pushed, ExitCode), pushed
        after_push = _casefold_set(read_text_words(dictionary, quiet=True))
        assert after_push == after_pull1

        pull2 = run.pull_into_wordlist()
        assert not isinstance(pull2, ExitCode), pull2
        after_pull2 = _casefold_set(read_text_words(wordlist, quiet=True))
        assert after_pull2 == after_pull1
        assert after_pull2 == _casefold_set(read_text_words(dictionary, quiet=True))
