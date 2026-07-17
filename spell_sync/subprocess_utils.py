"""Shared helpers for subprocess error handling."""

from __future__ import annotations


def trim_subprocess_text(text: str, *, limit: int = 500) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "… [truncated]"
