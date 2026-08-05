"""Harness CLI field-block helpers."""

from __future__ import annotations

from scripts.cli_text import format_field_block, format_kv_lines


def test_single_field_no_invented_pad() -> None:
    assert format_field_block([("synced", "ok")]) == "synced: ok"


def test_multi_field_alignment() -> None:
    text = format_field_block(
        [
            ("necessity", "commit-gate-sufficient"),
            ("reason", "ci-input-dirty"),
        ]
    )
    lines = text.splitlines()
    assert lines[0].startswith("necessity:")
    assert lines[1].startswith("reason:")
    assert lines[0].index("commit") == lines[1].index("ci-input")


def test_kv_lines() -> None:
    assert format_kv_lines([("A", "1"), ("B", "2")]) == "A=1\nB=2"
