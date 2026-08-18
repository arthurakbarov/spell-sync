"""Safe logging helpers and redaction."""

import logging
import re

_SENSITIVE_PATTERNS = (
    re.compile(r"(?i)(password|secret|token|api[_-]?key)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(removed words|wordlist content|dictionary content|full environment)\s*[:=]"),
    re.compile(r"(?i)\[chrome\s*=\s*true\]"),
    re.compile(r"(?i)/Users/[^\s]+"),
    re.compile(r"(?i)/home/[^\s]+"),
)

_FORBIDDEN_SUBSTRINGS = (
    "removed words:",
    "wordlist content:",
    "dictionary content:",
    "full environment:",
    "wordlist.txt",
    "spell-sync.toml",
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


def format_safe_log_record(record: logging.LogRecord, formatted: str) -> str:
    if getattr(record, "structured_event", False):
        return formatted
    if isinstance(record.msg, str):
        record.msg = sanitize_log_message(record.msg)
    if record.exc_info:
        exc_type = record.exc_info[0]
        type_name = exc_type.__name__ if exc_type is not None else "Exception"
        reason = getattr(record, "reason_code", None)
        suffix = f" exception_type={type_name}"
        if reason:
            suffix += f" reason_code={reason}"
        first_line = formatted.splitlines()[0] if formatted else ""
        return sanitize_log_message(first_line) + suffix
    return _sanitize_formatted_output(formatted)


def _sanitize_formatted_output(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        if re.match(r"^\s*\w+(Error|Exception):", line):
            lines.append(re.sub(r"(:\s*).+", r"\1[sanitized exception message]", line, count=1))
            continue
        if line.lstrip().startswith("File "):
            lines.append("  File [redacted]")
            continue
        lines.append(sanitize_log_message(line))
    return "\n".join(lines)
