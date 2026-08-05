#!/usr/bin/env python3
"""ASCII field-block helpers for maintainer / agent harness stdout."""

from __future__ import annotations


def format_field_block(pairs: list[tuple[str, str]]) -> str:
    """Align ``key: value`` within one block (nix-style).

    Pad after ``:`` so values share a column. Width is the longest key in this
    block only, plus one for ``:``. A single-field block does not invent pad.
    """
    if not pairs:
        return ""
    if len(pairs) == 1:
        key, value = pairs[0]
        return f"{key}: {value}"
    max_key = max(len(key) for key, _ in pairs)
    width = max_key + 1
    lines: list[str] = []
    for key, value in pairs:
        lines.append(f"{f'{key}:':<{width}} {value}")
    return "\n".join(lines)


def format_kv_lines(pairs: list[tuple[str, str]]) -> str:
    """Emit ``KEY=value`` lines (agent_context / DEV_LOOP style)."""
    return "\n".join(f"{key}={value}" for key, value in pairs)
