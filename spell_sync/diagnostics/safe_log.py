"""Safe logging helpers and redaction."""

from __future__ import annotations

import re
from typing import Any

_SENSITIVE_PATTERNS = (
    re.compile(r"(?i)(password|secret|token|api[_-]?key)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(removed words|wordlist content|dictionary content|full environment)\s*[:=]"),
)

_FORBIDDEN_SUBSTRINGS = (
    "removed words:",
    "wordlist content:",
    "dictionary content:",
    "full environment:",
)


def sanitize_log_message(message: str) -> str:
    lowered = message.lower()
    for token in _FORBIDDEN_SUBSTRINGS:
        if token in lowered:
            return "[redacted diagnostic message]"
    cleaned = message
    for pattern in _SENSITIVE_PATTERNS:
        cleaned = pattern.sub("[redacted]", cleaned)
    return cleaned


def sanitize_exception_message(message: str | None) -> str | None:
    if message is None:
        return None
    cleaned = sanitize_log_message(message)
    if cleaned != message:
        return "[sanitized exception message]"
    return message


def safe_repr(value: Any) -> str:
    return f"{type(value).__name__}"
