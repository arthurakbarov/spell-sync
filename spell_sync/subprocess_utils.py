"""Shared helpers for subprocess error handling."""


def trim_subprocess_text(text: str, *, limit: int = 500) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "... [truncated]"
