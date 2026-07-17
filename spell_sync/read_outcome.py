"""Typed dictionary read outcomes (missing, empty, corrupt, …).

One full-file parse produces an immutable ``DictionaryReadResult``. Push planning
and push both consume that model; there is no approximate sample-then-reread path.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .dictionaries import Dictionary, DictionaryFormat
from .io import _jetbrains_words_from_xml, detect_encoding_from_bytes, is_path_readable
from .words import WordSet, normalize_token


class ReadStatus(str, Enum):
    OK = "ok"
    MISSING = "missing"
    EMPTY = "empty"
    UNREADABLE = "unreadable"
    CORRUPT = "corrupt"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class FileFingerprint:
    """Identity of a dictionary file at read time (for conflict detection)."""

    size: int
    mtime_ns: int
    sha256: str


@dataclass(frozen=True)
class DictionaryReadResult:
    """Immutable result of one full dictionary read/parse."""

    status: ReadStatus
    words: frozenset[str]
    detail: str | None
    fingerprint: FileFingerprint | None


def _fingerprint(path: Path, raw: bytes) -> FileFingerprint:
    try:
        st = path.stat()
        size = st.st_size
        mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))
    except OSError:
        size = len(raw)
        mtime_ns = 0
    return FileFingerprint(
        size=size,
        mtime_ns=mtime_ns,
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def fingerprint_matches(path: Path, expected: FileFingerprint | None) -> bool:
    """True when ``path`` still matches ``expected`` (or both absent)."""
    if expected is None:
        return not path.exists() and not path.is_symlink()
    if not path.is_file():
        return False
    try:
        raw = path.read_bytes()
    except OSError:
        return False
    current = _fingerprint(path, raw)
    return current.sha256 == expected.sha256 and current.size == expected.size


def dictionary_read_result(dictionary: Dictionary) -> DictionaryReadResult:
    """Classify and (when possible) parse a dictionary in a single full-file pass."""
    path = Path(dictionary.path)
    if not path.exists() and not path.is_symlink():
        return DictionaryReadResult(ReadStatus.MISSING, frozenset(), None, None)
    if not is_path_readable(path):
        return DictionaryReadResult(ReadStatus.UNREADABLE, frozenset(), "unreadable", None)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return DictionaryReadResult(ReadStatus.UNREADABLE, frozenset(), str(exc), None)
    if len(raw) == 0:
        return DictionaryReadResult(ReadStatus.EMPTY, frozenset(), None, _fingerprint(path, raw))

    fmt = dictionary.format
    if fmt == DictionaryFormat.JSON:
        return _json_read_result(path, raw)
    if fmt == DictionaryFormat.JETBRAINS:
        return _jetbrains_read_result(path, raw)
    if fmt in (DictionaryFormat.TEXT, DictionaryFormat.HUNSPELL):
        return _text_like_read_result(path, raw)
    if fmt == DictionaryFormat.CHROME:
        return _chrome_read_result(path, raw)
    return DictionaryReadResult(
        ReadStatus.UNSUPPORTED,
        frozenset(),
        "unknown format",
        _fingerprint(path, raw),
    )


_CHECKSUM_LINE_RE = re.compile(r"^checksum_v1 = ([0-9a-fA-F]{32})\s*$")


def is_readable_for_push(status: ReadStatus) -> bool:
    """True when push may create or overwrite this target."""
    return status in (ReadStatus.OK, ReadStatus.MISSING, ReadStatus.EMPTY)


def is_readable_for_union(status: ReadStatus) -> bool:
    """True when pull or status may read words from this target."""
    return status in (ReadStatus.OK, ReadStatus.MISSING, ReadStatus.EMPTY)


def _json_read_result(path: Path, raw: bytes) -> DictionaryReadResult:
    fp = _fingerprint(path, raw)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        return DictionaryReadResult(ReadStatus.CORRUPT, frozenset(), str(exc), fp)
    if not isinstance(data, dict):
        return DictionaryReadResult(ReadStatus.CORRUPT, frozenset(), "root not object", fp)
    added = data.get("added_words", [])
    if added is None:
        return DictionaryReadResult(ReadStatus.CORRUPT, frozenset(), "added_words is null", fp)
    if not isinstance(added, list):
        return DictionaryReadResult(
            ReadStatus.UNSUPPORTED,
            frozenset(),
            "added_words not a list",
            fp,
        )
    words = frozenset(str(item) for item in added if isinstance(item, str) and item)
    if not words:
        return DictionaryReadResult(ReadStatus.EMPTY, frozenset(), None, fp)
    return DictionaryReadResult(ReadStatus.OK, words, None, fp)


def _jetbrains_read_result(path: Path, raw: bytes) -> DictionaryReadResult:
    fp = _fingerprint(path, raw)
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        return DictionaryReadResult(ReadStatus.CORRUPT, frozenset(), str(exc), fp)
    if not text.strip():
        return DictionaryReadResult(ReadStatus.EMPTY, frozenset(), None, fp)
    words, _, parsed = _jetbrains_words_from_xml(text)
    if not parsed:
        return DictionaryReadResult(ReadStatus.CORRUPT, frozenset(), "xml parse failed", fp)
    frozen = frozenset(words)
    if not frozen:
        return DictionaryReadResult(ReadStatus.EMPTY, frozen, None, fp)
    return DictionaryReadResult(ReadStatus.OK, frozen, None, fp)


def _text_words_from_text(text: str) -> WordSet:
    words: WordSet = set()
    for line in text.splitlines():
        if line.strip().startswith("#"):
            continue
        token = normalize_token(line)
        if token:
            words.add(token)
    return words


def _text_like_read_result(path: Path, raw: bytes) -> DictionaryReadResult:
    """Decode and classify the entire text dictionary file."""
    fp = _fingerprint(path, raw)
    encoding = detect_encoding_from_bytes(raw[:65536])
    if encoding is None:
        return DictionaryReadResult(ReadStatus.CORRUPT, frozenset(), "encoding unknown", fp)
    try:
        text = raw.decode(encoding)
    except UnicodeError as exc:
        return DictionaryReadResult(ReadStatus.CORRUPT, frozenset(), str(exc), fp)

    words = _text_words_from_text(text)
    frozen = frozenset(words)
    if not frozen:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            return DictionaryReadResult(ReadStatus.OK, frozenset(), None, fp)
        return DictionaryReadResult(ReadStatus.EMPTY, frozenset(), None, fp)
    return DictionaryReadResult(ReadStatus.OK, frozen, None, fp)


def _chrome_read_result(path: Path, raw: bytes) -> DictionaryReadResult:
    """Parse Chrome Custom Dictionary.txt with checksum_v1 validation."""
    fp = _fingerprint(path, raw)
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        return DictionaryReadResult(ReadStatus.CORRUPT, frozenset(), str(exc), fp)

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    if not text:
        return DictionaryReadResult(ReadStatus.EMPTY, frozenset(), None, fp)

    lines = text.splitlines(keepends=True)
    checksum_indices = [
        index for index, line in enumerate(lines) if line.rstrip("\n").startswith("checksum_v1")
    ]
    if not checksum_indices:
        return DictionaryReadResult(
            ReadStatus.CORRUPT,
            frozenset(),
            "missing checksum_v1 line",
            fp,
        )
    if len(checksum_indices) > 1:
        return DictionaryReadResult(
            ReadStatus.CORRUPT,
            frozenset(),
            "multiple checksum_v1 lines",
            fp,
        )

    checksum_index = checksum_indices[0]
    checksum_line = lines[checksum_index].rstrip("\r\n")
    match = _CHECKSUM_LINE_RE.match(checksum_line)
    if match is None:
        return DictionaryReadResult(
            ReadStatus.CORRUPT,
            frozenset(),
            "malformed checksum_v1 line",
            fp,
        )
    expected = match.group(1).lower()

    trailing = "".join(lines[checksum_index + 1 :])
    if trailing.strip():
        return DictionaryReadResult(
            ReadStatus.CORRUPT,
            frozenset(),
            "trailing data after checksum",
            fp,
        )

    body = "".join(lines[:checksum_index])
    actual = hashlib.md5(body.encode("utf-8")).hexdigest()
    if actual != expected:
        return DictionaryReadResult(
            ReadStatus.CORRUPT,
            frozenset(),
            "checksum mismatch",
            fp,
        )

    words: WordSet = set()
    for line in body.splitlines():
        token = normalize_token(line.rstrip("\n"))
        if token:
            words.add(token)
    frozen = frozenset(words)
    if not frozen and body.strip():
        return DictionaryReadResult(ReadStatus.CORRUPT, frozenset(), "no valid words", fp)
    if not frozen:
        return DictionaryReadResult(ReadStatus.EMPTY, frozenset(), None, fp)
    return DictionaryReadResult(ReadStatus.OK, frozen, None, fp)
