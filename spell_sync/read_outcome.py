"""Typed dictionary read outcomes (missing, empty, corrupt, ...).

One full-file parse produces an immutable ``DictionaryReadResult``. Push planning
and push both consume that model; there is no approximate sample-then-reread path.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .dictionary_model import Dictionary, DictionaryFormat
from .io import (
    _jetbrains_words_from_xml,
    detect_encoding_from_bytes,
    is_path_readable,
    parse_hunspell_text,
)
from .words import WordSet, is_hard_junk, normalize_token


class ReadStatus(StrEnum):
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
    except OSError:
        return DictionaryReadResult(ReadStatus.UNREADABLE, frozenset(), "unreadable", None)
    if len(raw) == 0:
        return DictionaryReadResult(ReadStatus.EMPTY, frozenset(), None, _fingerprint(path, raw))

    fmt = dictionary.format
    if fmt == DictionaryFormat.JSON:
        return _json_read_result(path, raw)
    if fmt == DictionaryFormat.JETBRAINS:
        return _jetbrains_read_result(path, raw)
    if fmt == DictionaryFormat.HUNSPELL:
        return _hunspell_read_result(path, raw)
    if fmt == DictionaryFormat.TEXT:
        return _text_like_read_result(path, raw)
    if fmt == DictionaryFormat.CHROME:
        return _chrome_read_result(path, raw)
    return DictionaryReadResult(
        ReadStatus.UNSUPPORTED,
        frozenset(),
        "unknown format",
        _fingerprint(path, raw),
    )


_CHECKSUM_LINE_RE = re.compile(r"^checksum_v1 = ([0-9a-fA-F]{32})$")


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
    if "added_words" not in data:
        return DictionaryReadResult(
            ReadStatus.CORRUPT,
            frozenset(),
            "missing added_words field",
            fp,
        )
    added = data["added_words"]
    if added is None:
        return DictionaryReadResult(ReadStatus.CORRUPT, frozenset(), "added_words is null", fp)
    if not isinstance(added, list):
        return DictionaryReadResult(
            ReadStatus.UNSUPPORTED,
            frozenset(),
            "added_words not a list",
            fp,
        )
    words: set[str] = set()
    for item in added:
        if not isinstance(item, str):
            return DictionaryReadResult(
                ReadStatus.CORRUPT,
                frozenset(),
                "added_words contains a non-string entry",
                fp,
            )
        token = normalize_token(item)
        if not token:
            continue
        if is_hard_junk(token):
            return DictionaryReadResult(
                ReadStatus.CORRUPT,
                frozenset(),
                "added_words contains an invalid token",
                fp,
            )
        words.add(token)
    if not words:
        return DictionaryReadResult(ReadStatus.EMPTY, frozenset(), None, fp)
    return DictionaryReadResult(ReadStatus.OK, frozenset(words), None, fp)


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
    cleaned: set[str] = set()
    for word in words:
        if is_hard_junk(word):
            return DictionaryReadResult(
                ReadStatus.CORRUPT,
                frozenset(),
                "invalid dictionary token",
                fp,
            )
        cleaned.add(word)
    frozen = frozenset(cleaned)
    if not frozen:
        return DictionaryReadResult(ReadStatus.EMPTY, frozen, None, fp)
    return DictionaryReadResult(ReadStatus.OK, frozen, None, fp)


def _hunspell_read_result(path: Path, raw: bytes) -> DictionaryReadResult:
    """Parse Hunspell ``.dic`` grammar (count header + optional ``word/FLAGS``)."""
    fp = _fingerprint(path, raw)
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        return DictionaryReadResult(ReadStatus.CORRUPT, frozenset(), str(exc), fp)
    if any(ord(ch) < 32 and ch not in "\t\n\r" for ch in text):
        return DictionaryReadResult(
            ReadStatus.CORRUPT,
            frozenset(),
            "control characters in hunspell dictionary",
            fp,
        )
    words, _affixes = parse_hunspell_text(text)
    for word in words:
        if is_hard_junk(word):
            return DictionaryReadResult(
                ReadStatus.CORRUPT,
                frozenset(),
                "invalid dictionary token",
                fp,
            )
    frozen = frozenset(words)
    if not frozen:
        return DictionaryReadResult(ReadStatus.EMPTY, frozenset(), None, fp)
    return DictionaryReadResult(ReadStatus.OK, frozen, None, fp)


def _text_words_from_text(text: str) -> WordSet | None:
    """Parse text dictionary words. None means the file contains hard junk."""
    words: WordSet = set()
    for line in text.splitlines():
        if line.strip().startswith("#"):
            continue
        token = normalize_token(line)
        if not token:
            continue
        if is_hard_junk(token):
            return None
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

    # Reject embedded C0 controls (other than tab/newline/CR) before tokenizing.
    if any(ord(ch) < 32 and ch not in "\t\n\r" for ch in text):
        return DictionaryReadResult(
            ReadStatus.CORRUPT,
            frozenset(),
            "control characters in dictionary text",
            fp,
        )

    words = _text_words_from_text(text)
    if words is None:
        return DictionaryReadResult(
            ReadStatus.CORRUPT,
            frozenset(),
            "invalid dictionary token",
            fp,
        )
    frozen = frozenset(words)
    if not frozen:
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
    # Reject embedded C0 controls other than LF before checksum validation.
    if any(ord(ch) < 32 and ch != "\n" for ch in text):
        return DictionaryReadResult(
            ReadStatus.CORRUPT,
            frozenset(),
            "control characters in chrome dictionary",
            fp,
        )

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
    checksum_line = lines[checksum_index].rstrip("\n")
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
    if trailing:
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
        if not token:
            continue
        if is_hard_junk(token):
            return DictionaryReadResult(
                ReadStatus.CORRUPT,
                frozenset(),
                "invalid dictionary token",
                fp,
            )
        words.add(token)
    frozen = frozenset(words)
    if not frozen and body.strip():
        return DictionaryReadResult(ReadStatus.CORRUPT, frozenset(), "no valid words", fp)
    if not frozen:
        return DictionaryReadResult(ReadStatus.EMPTY, frozenset(), None, fp)
    return DictionaryReadResult(ReadStatus.OK, frozen, None, fp)
