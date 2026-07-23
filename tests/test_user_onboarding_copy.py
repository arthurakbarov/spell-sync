"""User onboarding copy is present in product concepts."""

from __future__ import annotations

from spell_sync.application import product_concepts as pc


def test_collect_and_update_labels() -> None:
    assert "Collect" in pc.COLLECT_WORDS_TECHNICAL
    assert "Update" in pc.UPDATE_APPS_TECHNICAL
    assert "Pull" in pc.COLLECT_WORDS_TECHNICAL
    assert "Push" in pc.UPDATE_APPS_TECHNICAL


def test_safety_copy() -> None:
    assert "Nothing will be removed" in pc.PULL_PREVIEW_SAFETY
    assert "may be removed" in pc.PUSH_PREVIEW_SAFETY.lower()
    assert "never" in pc.BUILTIN_DICTIONARY_GUARANTEE.lower()


def test_problem_statement() -> None:
    assert "personal words" in pc.USER_PROBLEM_STATEMENT.lower()
