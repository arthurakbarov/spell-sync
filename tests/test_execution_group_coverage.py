"""Stable pytest groups must cover the full suite."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from scripts.test_groups import (  # noqa: E402
    GROUP_ORDER,
    group_files,
    is_pytest_group,
    validate_union,
)


def test_union_covers_all_tests() -> None:
    ok, problems = validate_union(ROOT)
    assert ok, problems


def test_each_group_has_files() -> None:
    for group_id in GROUP_ORDER:
        assert group_files(group_id, root=ROOT), group_id


def test_is_pytest_group() -> None:
    assert is_pytest_group("tests:rest")
    assert not is_pytest_group("mypy")
