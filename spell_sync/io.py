"""Read and write dictionaries (atomic, with backup)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator, Union

from .config import CHROME_CHECKSUM_PREFIX, backup_keep_count
from .log import log
from .words import WordSet, normalize_token, sort_words

PathLike = Union[str, Path]

_ENCODINGS_TO_TRY = ("utf-8-sig", "utf-16", "utf-8", "cp1251")
_DETECT_SAMPLE_BYTES = 65536
_BACKUP_DISABLED = 0


# --- Helpers ---


def _is_quiet(explicit: bool | None) -> bool:
    if explicit is not None:
        return explicit
    return True


def _warn_read_failed(fmt: str, target: Path, exc: Exception | str, *, quiet: bool | None) -> None:
    if _is_quiet(quiet):
        return
    message = exc if isinstance(exc, str) else str(exc)
    log.warn(f"read failed ({fmt}) {target}: {message}; treating as empty")


def _warn_write_failed(path: PathLike, exc: Exception, *, quiet: bool | None) -> None:
    if _is_quiet(quiet):
        return
    log.warn(f"no write access {path}: {exc}")


def is_path_readable(path: PathLike) -> bool:
    """False when an existing path cannot be read (TCC / sandbox)."""
    target = Path(path)
    if not target.exists():
        return True
    if target.is_dir():
        try:
            return os.access(target, os.R_OK)
        except OSError:
            return False
    try:
        with open(target, "rb") as handle:
            handle.read(1)
        return True
    except (PermissionError, OSError):
        return False


def is_path_writable(path: PathLike) -> bool:
    """Probe real write capability without altering the target dictionary.

    Creates a temporary file in the parent directory and (when the target exists)
    verifies a same-filesystem rename can succeed via a throwaway replace on a
    temp sibling. Never overwrites or truncates ``path``.
    """
    target = Path(path)
    parent = target.parent if target.name else target
    try:
        if not parent.is_dir():
            return False
        fd, temp_name = tempfile.mkstemp(
            prefix=".spell-sync-write-probe.",
            suffix=".tmp",
            dir=str(parent),
        )
    except OSError:
        return False
    temp = Path(temp_name)
    try:
        try:
            os.write(fd, b"0")
            os.fsync(fd)
        finally:
            os.close(fd)
        probe = parent / f".spell-sync-write-probe.{os.getpid()}.rpl"
        try:
            os.replace(temp, probe)
            probe.unlink(missing_ok=True)
        except OSError:
            return False
        if target.exists() and target.is_symlink():
            return False
        if target.is_file() and not os.access(target, os.W_OK):
            return False
        return True
    except OSError:  # pragma: no cover -- unexpected probe failure after temp create
        return False
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:  # pragma: no cover -- cleanup race
            pass


def ensure_parent_dir(path: PathLike) -> None:
    parent = Path(path).parent
    if str(parent) and not parent.is_dir():
        parent.mkdir(parents=True, exist_ok=True)


def detect_encoding_from_bytes(sample: bytes) -> str | None:
    """Detect encoding from a byte prefix (same rules as ``detect_encoding``)."""
    for encoding in _ENCODINGS_TO_TRY:
        try:
            sample.decode(encoding)
            return encoding
        except (UnicodeError, LookupError):
            continue
    return None


def detect_encoding(path: PathLike) -> str | None:
    """Detect encoding from the file header (without reading the whole dictionary)."""
    target = Path(path)
    if not target.exists():
        return None
    try:
        sample = target.read_bytes()[:_DETECT_SAMPLE_BYTES]
    except (PermissionError, OSError):
        return None
    return detect_encoding_from_bytes(sample)


# --- Atomic write ---


def rotate_backup_chain(backup: Path, *, keep: int) -> None:
    """
    Shift numbered backups before overwriting `.bak`.

    keep=3 retains `.bak`, `.bak.1`, `.bak.2` (newest → oldest).
    keep=1 keeps only `.bak` (no rotation).
    """
    if keep <= 1:
        return
    max_index = keep - 1

    def slot_path(index: int) -> Path:
        return backup if index == 0 else Path(f"{backup}.{index}")

    try:
        slot_path(max_index).unlink(missing_ok=True)
    except OSError:
        pass
    for index in range(max_index, 0, -1):
        src = slot_path(index - 1)
        dst = slot_path(index)
        if not src.exists():
            continue
        try:
            src.rename(dst)
        except OSError:
            pass


def create_bak_backup(destination: Path) -> bool:
    """
    Create/rotate `.bak` backup for an existing file.

    Returns True on success or when backups are disabled; False when backup was required but failed.
    """
    if not destination.exists():
        return True
    keep = backup_keep_count()
    if keep <= 0:
        return True
    backup = destination.with_suffix(destination.suffix + ".bak")
    rotate_backup_chain(backup, keep=keep)
    try:
        shutil.copy2(destination, backup)
    except OSError as exc:
        log.warn(f"backup not created {backup}: {exc}")
        return False
    return True


def _backups_allowed() -> bool:
    return _BACKUP_DISABLED <= 0


def _disable_backups() -> None:
    global _BACKUP_DISABLED
    _BACKUP_DISABLED += 1


def _enable_backups() -> None:
    global _BACKUP_DISABLED
    _BACKUP_DISABLED = max(0, _BACKUP_DISABLED - 1)


@contextmanager
def backups_disabled() -> Iterator[None]:
    """Temporarily disable `.bak` creation inside `atomic_write`."""
    _disable_backups()
    try:
        yield
    finally:
        _enable_backups()


def physical_path(path: PathLike) -> Path:
    """
    Physical path for I/O (backup, write, rollback).

    Symlinks are not replaced — work with the resolve()-target.
    """
    target = Path(path)
    if not target.is_symlink():
        return target
    try:
        return target.resolve()
    except OSError:
        return target


def wordlist_unreadable(path: PathLike) -> bool:
    """True when the file exists but cannot be read (TCC / sandbox)."""
    target = Path(path)
    return target.exists() and not is_path_readable(path)


def atomic_write(path: PathLike, data: bytes, *, keep_backup: bool = True) -> None:
    target = Path(path)
    destination = physical_path(target)
    ensure_parent_dir(destination)
    if keep_backup and destination.exists() and _backups_allowed():
        create_bak_backup(destination)
    # Create a unique temp file in the destination directory to avoid collisions
    # in parallel runs and to keep os.replace() on the same filesystem.
    fd, temp_name = tempfile.mkstemp(
        prefix=destination.name + ".",
        suffix=".tmp",
        dir=str(destination.parent),
    )
    temp = Path(temp_name)
    try:
        try:
            handle = os.fdopen(fd, "wb")
        except OSError:
            os.close(fd)
            raise
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, destination)
    except OSError:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


# --- Text dictionaries ---


def read_text_words(path: PathLike, *, quiet: bool | None = None) -> WordSet:
    target = Path(path)
    if not target.exists():
        return set()
    try:
        encoding = detect_encoding(target) or "utf-8"
        words: WordSet = set()
        with open(target, "r", encoding=encoding, errors="strict") as handle:
            for line in handle:
                if line.strip().startswith("#"):
                    continue
                token = normalize_token(line)
                if token:
                    words.add(token)
    except (PermissionError, OSError, UnicodeError) as exc:
        _warn_read_failed("text", target, exc, quiet=quiet)
        return set()
    if not _is_quiet(quiet):
        log.dictionary_read(len(words), encoding, str(target))
    return words


def _text_payload_bytes(payload: str, encoding: str, bom: bool) -> bytes:
    if bom and encoding.lower().replace("-", "") == "utf16le":
        return b"\xff\xfe" + payload.encode("utf-16-le")
    return payload.encode(encoding)


def write_text_words(
    path: PathLike,
    words: Iterable[str],
    encoding: str,
    bom: bool,
    *,
    quiet: bool | None = None,
) -> bool:
    sorted_words = sort_words(words)
    payload = "\n".join(sorted_words) + "\n"
    data = _text_payload_bytes(payload, encoding, bom)
    try:
        atomic_write(path, data)
    except (PermissionError, OSError) as exc:
        _warn_write_failed(path, exc, quiet=quiet)
        return False
    if not _is_quiet(quiet):
        log.dictionary_write(len(sorted_words), encoding, str(path))
    return True


# --- Hunspell (UTF-8 plain text, optional # comments) ---

_HUNSPELL_AFFIX_BY_PATH: dict[str, dict[str, str]] = {}


def _parse_hunspell_line(line: str) -> tuple[str | None, str | None]:
    """Return (word, affix_suffix). Both None when the line should be skipped."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith("*"):
        return None, None
    if "/" in stripped:
        word_part, affix = stripped.split("/", 1)
        token = normalize_token(word_part)
        if not token:
            return None, None
        return token, affix
    token = normalize_token(stripped)
    if not token:
        return None, None
    return token, None


def read_hunspell_words(path: PathLike, *, quiet: bool | None = None) -> WordSet:
    target = Path(path)
    if not target.exists():
        return set()
    words: WordSet = set()
    affix_map: dict[str, str] = {}
    try:
        with open(target, "r", encoding="utf-8", errors="strict") as handle:
            first_line = True
            for line in handle:
                if first_line:
                    first_line = False
                    if line.strip().isdigit():
                        continue
                word, affix = _parse_hunspell_line(line)
                if word is None:
                    continue
                words.add(word)
                if affix is not None:
                    affix_map[word] = affix
    except UnicodeError as exc:
        _warn_read_failed("hunspell", target, exc, quiet=quiet)
        _HUNSPELL_AFFIX_BY_PATH[str(target)] = {}
        return set()
    except (PermissionError, OSError) as exc:
        _warn_read_failed("hunspell", target, exc, quiet=quiet)
        return set()
    _HUNSPELL_AFFIX_BY_PATH[str(target)] = affix_map
    if not _is_quiet(quiet):
        log.dictionary_read(len(words), "hunspell", str(target))
    return words


def write_hunspell_words(
    path: PathLike,
    words: Iterable[str],
    *,
    quiet: bool | None = None,
) -> bool:
    target = Path(path)
    # Refresh cached affixes from the current file on disk (if readable).
    if target.exists():
        read_hunspell_words(target, quiet=True)
    affix_map = _HUNSPELL_AFFIX_BY_PATH.get(str(target), {})
    sorted_words = sort_words(words)

    def _format_word(word: str) -> str:
        affix = affix_map.get(word)
        if affix:
            return f"{word}/{affix}"
        return word

    payload = "\n".join(_format_word(word) for word in sorted_words) + "\n"
    try:
        atomic_write(path, payload.encode("utf-8"))
    except (PermissionError, OSError) as exc:
        _warn_write_failed(path, exc, quiet=quiet)
        return False
    _HUNSPELL_AFFIX_BY_PATH[str(target)] = {
        word: affix for word in sorted_words if (affix := affix_map.get(word))
    }
    if not _is_quiet(quiet):
        log.dictionary_write(len(sorted_words), "hunspell", str(path))
    return True


# --- JSON (Sublime) ---


def read_json_words(path: PathLike, *, quiet: bool | None = None) -> WordSet:
    target = Path(path)
    if not target.exists():
        return set()
    try:
        with open(target, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        _warn_read_failed("json", target, exc, quiet=quiet)
        return set()
    except (OSError, PermissionError) as exc:
        _warn_read_failed("json", target, exc, quiet=quiet)
        return set()
    added = data.get("added_words", []) if isinstance(data, dict) else []
    words = {normalize_token(word) for word in added if isinstance(word, str)}
    words.discard("")
    if not _is_quiet(quiet):
        log.dictionary_read(len(words), "json", str(target))
    return words


def write_json_words(
    path: PathLike,
    words: Iterable[str],
    *,
    quiet: bool | None = None,
) -> bool:
    sorted_words = sort_words(words)
    payload = (
        json.dumps(
            {"added_words": sorted_words},
            ensure_ascii=False,
            indent=4,
            sort_keys=True,
        )
        + "\n"
    )
    try:
        atomic_write(path, payload.encode("utf-8"))
    except (PermissionError, OSError) as exc:
        _warn_write_failed(path, exc, quiet=quiet)
        return False
    if not _is_quiet(quiet):
        log.dictionary_write(len(sorted_words), "json", str(path))
    return True


# --- Chrome (checksum_v1) ---


def read_chrome_words(path: PathLike, *, quiet: bool | None = None) -> WordSet:
    target = Path(path)
    if not target.exists():
        return set()
    words: WordSet = set()
    try:
        with open(target, "r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                token = normalize_token(line.rstrip("\n"))
                if not token or token.startswith("checksum_v1"):
                    continue
                words.add(token)
    except (PermissionError, OSError) as exc:
        _warn_read_failed("chrome", target, exc, quiet=quiet)
        return set()
    if not _is_quiet(quiet):
        log.dictionary_read(len(words), "chrome", str(target))
    return words


def write_chrome_words(
    path: PathLike,
    words: Iterable[str],
    *,
    quiet: bool | None = None,
) -> bool:
    sorted_words = sort_words(words)
    body = "".join(word + "\n" for word in sorted_words)
    checksum = hashlib.md5(body.encode("utf-8")).hexdigest()
    try:
        atomic_write(path, (body + CHROME_CHECKSUM_PREFIX + checksum).encode("utf-8"))
    except (PermissionError, OSError) as exc:
        _warn_write_failed(path, exc, quiet=quiet)
        return False
    if not _is_quiet(quiet):
        log.dictionary_write(len(sorted_words), "chrome", str(path))
    return True


# --- JetBrains (cachedDictionary.xml / spellchecker-dictionary.xml) ---


def _warn_jetbrains(path: Path, message: str) -> None:
    """
    Emit JetBrains corruption warnings unless output is globally quiet.

    This preserves "always warn on corrupt JetBrains XML" in normal interactive runs, but avoids
    breaking `--json` purity (where `quiet_json_output()` sets `log.quiet = True`).
    """
    if log.quiet:
        return
    log.warn(f"{message} {path}")


def _jetbrains_words_from_xml(text: str) -> tuple[WordSet, str | None, bool]:
    words: WordSet = set()
    component_name: str | None = None
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return words, None, False
    for component in root.iter("component"):
        words_elem = component.find("words")
        if words_elem is None:
            continue
        component_name = component.get("name") or "CachedDictionaryState"
        for elem in words_elem.findall("w"):
            token = normalize_token((elem.text or "").strip())
            if token:
                words.add(token)
        break
    if component_name is None:
        return words, None, False
    return words, component_name, True


def read_jetbrains_words(path: PathLike, *, quiet: bool | None = None) -> WordSet:
    """Read JetBrains XML for pull/union paths; parse errors return empty with a warning.

    Push uses ``dictionary_read_result()`` first and skips corrupt JetBrains files.
    """
    target = Path(path)
    if not target.exists():
        return set()
    try:
        text = target.read_text(encoding="utf-8", errors="ignore")
    except (PermissionError, OSError) as exc:
        if _is_quiet(quiet):
            return set()
        _warn_jetbrains(target, f"read failed (jetbrains) {exc}; treating as empty:")
        return set()
    if not text.strip():
        return set()
    words, _, parsed = _jetbrains_words_from_xml(text)
    if not parsed:
        if _is_quiet(quiet):
            return set()
        _warn_jetbrains(target, "read failed (jetbrains) parse error; treating as empty:")
        return set()
    if not _is_quiet(quiet):
        log.dictionary_read(len(words), "jetbrains", str(target))
    return words


def _jetbrains_component_name(path: PathLike) -> str:
    target = Path(path)
    if not target.exists():
        return "CachedDictionaryState"
    try:
        text = target.read_text(encoding="utf-8", errors="ignore")
    except (PermissionError, OSError):
        return "CachedDictionaryState"
    _, component_name, parsed = _jetbrains_words_from_xml(text)
    if parsed and component_name:
        return component_name
    return "CachedDictionaryState"


def write_jetbrains_words(
    path: PathLike,
    words: Iterable[str],
    *,
    quiet: bool | None = None,
) -> bool:
    sorted_words = sort_words(words)
    component_name = _jetbrains_component_name(path)
    root = ET.Element("application")
    component = ET.SubElement(root, "component", {"name": component_name})
    words_elem = ET.SubElement(component, "words")
    for word in sorted_words:
        w_elem = ET.SubElement(words_elem, "w")
        w_elem.text = word
    if sys.version_info >= (3, 9):
        ET.indent(root, space="  ")
    xml_body = ET.tostring(root, encoding="unicode")
    payload = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_body + "\n"
    try:
        atomic_write(path, payload.encode("utf-8"))
    except (PermissionError, OSError) as exc:
        _warn_write_failed(path, exc, quiet=quiet)
        return False
    if not _is_quiet(quiet):
        log.dictionary_write(len(sorted_words), "jetbrains", str(path))
    return True
