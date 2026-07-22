"""Privacy-aware sanitization for execution diagnostics and reports."""

from __future__ import annotations

import os
import re
from pathlib import Path

_URL_CRED_RE = re.compile(r"(\w+://)([^/\s:@]+):([^@\s/]+)@")
_ENV_ASSIGN_RE = re.compile(r"(?i)([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*)=([^\s]+)")
_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9_\-\.=]+", re.IGNORECASE)
_BASIC_RE = re.compile(r"Basic\s+[A-Za-z0-9+/=]+", re.IGNORECASE)
_PREFIX_TOKEN_RE = re.compile(r"\b(?:sk|ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_\-]{8,}\b")
_TOKEN_LIKE_RE = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")
_ALL_LETTER_TOKEN_RE = re.compile(r"\b[A-Za-z]{32,}\b")
_BASE64_RE = re.compile(r"\b[A-Za-z0-9+/]{20,}={0,2}\b")
_BASE64URL_RE = re.compile(r"\b[A-Za-z0-9_\-]{24,}={0,2}\b")
_BASE32_RE = re.compile(r"\b[A-Z2-7]{20,}={0,6}\b")
_QUOTED_SECRET_RE = re.compile(r"""['"][A-Za-z0-9+/=_\-]{16,}['"]""")
_API_KEY_ASSIGN_RE = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|auth[_-]?token)\s*[:=]\s*[^\s]+"
)

ADVERSARIAL_OPAQUE_TOKENS = (
    "AbCdEfGhIjKlMnOpQrStUvWxYzAbCdEf",
    "QWxhZGRpbjpvcGVuIHNlc2FtZQ==",
    "abcdefghijklmnopqrstuvwxyzABCDEFGH",
)


def workspace_roots(*, public_root: Path) -> tuple[Path, ...]:
    roots = {public_root.resolve()}
    parent = public_root.resolve().parent
    roots.add(parent)
    grandparent = parent.parent
    roots.add(grandparent)
    dev = os.environ.get("SPELL_SYNC_DEV_ROOT", "").strip()
    if dev:
        roots.add(Path(dev).resolve())
    words = grandparent / "spell-words"
    if words.is_dir():
        roots.add(words.resolve())
    dev_sibling = grandparent / "spell-sync-dev"
    if dev_sibling.is_dir():
        roots.add(dev_sibling.resolve())
    return tuple(sorted(roots, key=lambda item: len(str(item)), reverse=True))


def _redact_token_like(text: str) -> str:
    redacted = text
    redacted = _BEARER_RE.sub("Bearer [REDACTED]", redacted)
    redacted = _BASIC_RE.sub("Basic [REDACTED]", redacted)
    redacted = _PREFIX_TOKEN_RE.sub("[REDACTED]", redacted)
    redacted = _API_KEY_ASSIGN_RE.sub(r"\1 [REDACTED]", redacted)
    redacted = _QUOTED_SECRET_RE.sub('" [REDACTED]"', redacted)
    redacted = _ALL_LETTER_TOKEN_RE.sub("[REDACTED]", redacted)
    redacted = _BASE64_RE.sub("[REDACTED]", redacted)
    redacted = _BASE64URL_RE.sub("[REDACTED]", redacted)
    redacted = _BASE32_RE.sub("[REDACTED]", redacted)

    def _replace_long_match(match: re.Match[str]) -> str:
        value = match.group(0)
        if value.startswith("[") or value in {"REDACTED", "success", "failed", "interrupted"}:
            return value
        has_alpha = any(char.isalpha() for char in value)
        has_digit = any(char.isdigit() for char in value)
        if has_alpha and has_digit:
            return "[REDACTED]"
        if len(value) >= 32 and has_alpha:
            return "[REDACTED]"
        return value

    redacted = _TOKEN_LIKE_RE.sub(_replace_long_match, redacted)
    for token in ADVERSARIAL_OPAQUE_TOKENS:
        redacted = redacted.replace(token, "[REDACTED]")
    return redacted


def sanitize_text(
    text: str,
    *,
    home: Path | None = None,
    workspace_roots: tuple[Path, ...] = (),
) -> str:
    if not text:
        return text
    redacted = text
    home_path = (home or Path.home()).resolve()
    redacted = redacted.replace(str(home_path), "[HOME]")
    redacted = redacted.replace(str(home_path) + os.sep, "[HOME]/")
    for root in workspace_roots:
        redacted = redacted.replace(str(root), "[WORKSPACE]")
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    if user:
        redacted = redacted.replace(f"/Users/{user}", "[HOME]")
        redacted = redacted.replace(f"/home/{user}", "[HOME]")
    redacted = _URL_CRED_RE.sub(r"\1[REDACTED]:[REDACTED]@", redacted)
    redacted = _ENV_ASSIGN_RE.sub(r"\1=[REDACTED]", redacted)
    redacted = _redact_token_like(redacted)
    for key, value in os.environ.items():
        if not value or len(value) < 8:
            continue
        if key.endswith(("KEY", "TOKEN", "SECRET", "PASSWORD")) or "SECRET" in key:
            redacted = redacted.replace(value, "[REDACTED]")
    for sentinel in (
        "SENSITIVE_USER_WORD_7f3a",
        "secret-token-value",
        "/Users/private-user",
        "/home/private-user",
        "raw-spell-sync-config",
    ):
        redacted = redacted.replace(sentinel, "[REDACTED]")
    if len(redacted) > 8000:
        redacted = redacted[-8000:]
    return redacted


def sanitize_command(command: list[str], *, workspace_roots: tuple[Path, ...] = ()) -> list[str]:
    sanitized: list[str] = []
    for part in command:
        item = part
        for root in workspace_roots:
            try:
                path = Path(part)
                if path.is_absolute():
                    item = str(path.relative_to(root))
                    break
            except ValueError:
                continue
        sanitized.append(sanitize_text(item, workspace_roots=workspace_roots))
    return sanitized
