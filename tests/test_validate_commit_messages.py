"""Tests for commit message shape validation."""

from __future__ import annotations

from scripts.validate_commit_messages import CommitMessage, validate_history, validate_message


def test_subject_requires_trailing_period() -> None:
    errors = validate_message(
        CommitMessage(sha="abcd1234", subject="Add writer goldens", body=""),
        check_hygiene=False,
    )
    assert any("must end with '.'" in e for e in errors)


def test_conventional_prefix_forbidden() -> None:
    errors = validate_message(
        CommitMessage(sha="abcd1234", subject="feat: Add writer goldens.", body=""),
        check_hygiene=False,
    )
    assert any("Conventional Commit" in e for e in errors)


def test_hygiene_flag_detects_ruff_followup() -> None:
    errors = validate_message(
        CommitMessage(sha="abcd1234", subject="Format padding inventory for ruff.", body=""),
        check_hygiene=True,
    )
    assert any("hygiene follow-up" in e for e in errors)


def test_valid_message_passes() -> None:
    errors = validate_message(
        CommitMessage(
            sha="abcd1234",
            subject="Fill testing gaps with writer goldens and CLI budget.",
            body="Property sync and R-CON samples close the remaining matrix rows.",
        ),
        check_hygiene=True,
    )
    assert errors == []


def test_repo_history_shape_without_hygiene_flag() -> None:
    # Exercise against this repository: subject shape must already be unified.
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    errors = validate_history(repo, limit=20, check_hygiene=False)
    assert errors == [], errors
