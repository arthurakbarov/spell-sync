"""Read and write dictionaries (atomic, with backup)."""

import contextlib
import errno
import hashlib
import json
import os
import shutil
import stat
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path

from .config import CHROME_CHECKSUM_PREFIX, backup_keep_count
from .guest_messages import REPORT_ALREADY_EXISTS
from .log import log
from .runtime_settings import RuntimeSettings
from .words import WordSet, is_hard_junk, normalize_token, sort_words

type PathLike = str | Path

_ENCODINGS_TO_TRY = ("utf-8-sig", "utf-16", "utf-8", "cp1251")
_DETECT_SAMPLE_BYTES = 65536

# --- Helpers ---


def _is_quiet(explicit: bool | None) -> bool:
    if explicit is not None:
        return explicit
    return True


def _warn_read_failed(fmt: str, target: Path, *, quiet: bool | None) -> None:
    if _is_quiet(quiet):
        return
    log.warn(f"read failed ({fmt}) {target.name}; treating as empty")


def _warn_write_failed(path: PathLike, *, quiet: bool | None) -> None:
    if _is_quiet(quiet):
        return
    log.warn(f"no write access ({Path(path).name})")


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
    except PermissionError, OSError:
        return False


def is_path_writable(path: PathLike) -> bool:
    """Probe real write capability without altering the target dictionary.

    Creates unique temporary files in the parent directory (``tempfile.mkstemp``)
    and verifies a same-filesystem rename can succeed by replacing onto a second
    unique temp that this probe created. Never overwrites an unknown existing
    path or symlink.
    """
    target = Path(path)
    parent = target.parent if target.name else target
    try:
        if not parent.is_dir():
            return False
        fd, write_name = tempfile.mkstemp(
            prefix=".spell-sync-write-probe.",
            suffix=".tmp",
            dir=str(parent),
        )
    except OSError:
        return False
    write_temp = Path(write_name)
    rename_temp: Path | None = None
    try:
        try:
            os.write(fd, b"0")
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            rename_fd, rename_name = tempfile.mkstemp(
                prefix=".spell-sync-write-probe.",
                suffix=".rpl",
                dir=str(parent),
            )
        except OSError:
            return False
        os.close(rename_fd)
        rename_temp = Path(rename_name)
        try:
            # Destination is only the exclusive temp we created — never an unknown path.
            os.replace(write_temp, rename_temp)
            write_temp = rename_temp
            rename_temp = None
        except OSError:
            return False
        if target.exists() and target.is_symlink():
            return False
        return not (target.is_file() and not os.access(target, os.W_OK))
    except OSError:  # pragma: no cover -- unexpected probe failure after temp create
        return False
    finally:
        for leftover in (write_temp, rename_temp):
            if leftover is None:
                continue
            with contextlib.suppress(OSError):  # pragma: no cover -- cleanup race
                leftover.unlink(missing_ok=True)


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
        except UnicodeError, LookupError:
            continue
    return None


def detect_encoding(path: PathLike) -> str | None:
    """Detect encoding from the file header (without reading the whole dictionary)."""
    target = Path(path)
    if not target.exists():
        return None
    try:
        sample = target.read_bytes()[:_DETECT_SAMPLE_BYTES]
    except PermissionError, OSError:
        return None
    return detect_encoding_from_bytes(sample)


# --- Atomic write ---


def write_text_exclusive(path: PathLike, text: str, *, encoding: str = "utf-8") -> Path:
    """Create ``path`` exclusively and write ``text``.

    Raises ``FileExistsError`` if the destination already exists (no replace/overwrite).
    """
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        fd = os.open(destination, flags, 0o644)
    except FileExistsError:
        raise FileExistsError(REPORT_ALREADY_EXISTS) from None
    except OSError as exc:
        if exc.errno == errno.EEXIST:
            raise FileExistsError(REPORT_ALREADY_EXISTS) from exc
        raise
    try:
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            handle.write(text)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


def rotate_backup_chain(backup: Path, *, keep: int) -> None:
    """
    Shift numbered backups before overwriting ``.bak``.

    keep=3 retains ``name.bak``, ``name.1.bak``, ``name.2.bak`` (newest → oldest).
    Every slot ends with the constant ``.bak`` extension so macOS/duti can bind
    one handler (``.bak.1`` would register as extension ``1``).
    keep=1 keeps only ``.bak`` (no rotation).
    """
    if keep <= 1:
        return
    max_index = keep - 1

    def slot_path(index: int) -> Path:
        if index == 0:
            return backup
        name = backup.name
        if name.endswith(".bak"):
            stem = name[: -len(".bak")]
            return backup.with_name(f"{stem}.{index}.bak")
        return Path(f"{backup}.{index}")

    with contextlib.suppress(OSError):
        slot_path(max_index).unlink(missing_ok=True)
    for index in range(max_index, 0, -1):
        src = slot_path(index - 1)
        dst = slot_path(index)
        if not src.exists():
            continue
        with contextlib.suppress(OSError):
            src.rename(dst)


def create_bak_backup(
    destination: Path,
    *,
    settings: RuntimeSettings | None = None,
) -> bool:
    """
    Create/rotate `.bak` backup for an existing file.

    Returns True on success or when backups are disabled; False when backup was required but failed.
    """
    if not destination.exists():
        return True
    keep = backup_keep_count(settings=settings or RuntimeSettings.defaults())
    if keep <= 0:
        return True
    backup = destination.with_suffix(destination.suffix + ".bak")
    # Copy into a temp sibling first so a failed copy never rotates away history.
    fd, temp_name = tempfile.mkstemp(
        prefix=backup.name + ".",
        suffix=".partial",
        dir=str(backup.parent),
    )
    os.close(fd)
    temp = Path(temp_name)
    try:
        shutil.copy2(destination, temp)
        rotate_backup_chain(backup, keep=keep)
        os.replace(temp, backup)
    except OSError:
        with contextlib.suppress(OSError):
            temp.unlink(missing_ok=True)
        log.warn(f"backup not created ({backup.name})")
        return False
    return True


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
    """True when the file exists but cannot be read or decoded as text."""
    target = Path(path)
    if not target.exists():
        return False
    if not is_path_readable(path):
        return True
    try:
        encoding = detect_encoding(target) or "utf-8"
        with open(target, encoding=encoding, errors="strict") as handle:
            text = handle.read()
    except OSError, UnicodeError:
        return True
    # Canonical wordlist must not contain embedded C0 controls.
    return any(ord(ch) < 32 and ch not in "\t\n\r" for ch in text)


def atomic_write(
    path: PathLike,
    data: bytes,
    *,
    keep_backup: bool = True,
    settings: RuntimeSettings | None = None,
) -> None:
    target = Path(path)
    destination = physical_path(target)
    ensure_parent_dir(destination)
    # Preserve the existing file's permission bits; mkstemp defaults to 0600 and
    # os.replace() would otherwise silently tighten an existing 0644 dictionary.
    preserved_mode: int | None = None
    if destination.exists():
        try:
            preserved_mode = stat.S_IMODE(os.stat(destination).st_mode)
        except OSError:
            preserved_mode = None
    if (
        keep_backup
        and destination.exists()
        and not create_bak_backup(destination, settings=settings)
    ):
        raise OSError(f"backup failed for {destination.name}")
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
        if preserved_mode is not None:
            os.chmod(temp, preserved_mode)
        os.replace(temp, destination)
    except OSError:
        with contextlib.suppress(OSError):
            temp.unlink(missing_ok=True)
        raise


# --- Text dictionaries ---


def read_text_words(path: PathLike, *, quiet: bool | None = None) -> WordSet:
    target = Path(path)
    if not target.exists():
        return set()
    try:
        encoding = detect_encoding(target) or "utf-8"
        with open(target, encoding=encoding, errors="strict") as handle:
            text = handle.read()
    except PermissionError, OSError, UnicodeError:
        _warn_read_failed("text", target, quiet=quiet)
        return set()
    if any(ord(ch) < 32 and ch not in "\t\n\r" for ch in text):
        _warn_read_failed("text", target, quiet=quiet)
        return set()
    words: WordSet = set()
    for line in text.splitlines():
        if line.strip().startswith("#"):
            continue
        token = normalize_token(line)
        if not token or is_hard_junk(token):
            continue
        words.add(token)
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
    except PermissionError, OSError:
        _warn_write_failed(path, quiet=quiet)
        return False
    if not _is_quiet(quiet):
        log.dictionary_write(len(sorted_words), encoding, str(path))
    return True


# --- Hunspell (UTF-8 plain text, optional # comments) ---


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


def parse_hunspell_text(text: str) -> tuple[WordSet, dict[str, str]]:
    """Parse Hunspell ``.dic`` body into base words and affix flags (no global cache)."""
    words: WordSet = set()
    affix_map: dict[str, str] = {}
    first_line = True
    for line in text.splitlines():
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
    return words, affix_map


def load_hunspell_affixes(path: PathLike) -> dict[str, str]:
    """Fresh affix map from disk for the given path (empty when unreadable/missing)."""
    target = Path(path)
    if not target.is_file():
        return {}
    try:
        text = target.read_text(encoding="utf-8", errors="strict")
    except OSError, UnicodeError:
        return {}
    _words, affix_map = parse_hunspell_text(text)
    return affix_map


def format_hunspell_payload(words: Iterable[str], affix_map: dict[str, str]) -> bytes:
    """Encode sorted Hunspell lines, preserving affix flags when present."""

    def _format_word(word: str) -> str:
        affix = affix_map.get(word)
        if affix:
            return f"{word}/{affix}"
        return word

    payload = "\n".join(_format_word(word) for word in sort_words(words)) + "\n"
    return payload.encode("utf-8")


def read_hunspell_words(path: PathLike, *, quiet: bool | None = None) -> WordSet:
    target = Path(path)
    if not target.exists():
        return set()
    try:
        text = target.read_text(encoding="utf-8", errors="strict")
    except UnicodeError:
        _warn_read_failed("hunspell", target, quiet=quiet)
        return set()
    except PermissionError, OSError:
        _warn_read_failed("hunspell", target, quiet=quiet)
        return set()
    words, _affix_map = parse_hunspell_text(text)
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
    affix_map = load_hunspell_affixes(target) if target.exists() else {}
    sorted_words = sort_words(words)
    try:
        atomic_write(path, format_hunspell_payload(sorted_words, affix_map))
    except PermissionError, OSError:
        _warn_write_failed(path, quiet=quiet)
        return False
    if not _is_quiet(quiet):
        log.dictionary_write(len(sorted_words), "hunspell", str(path))
    return True


# --- JSON (Sublime) ---


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
    except PermissionError, OSError:
        _warn_write_failed(path, quiet=quiet)
        return False
    if not _is_quiet(quiet):
        log.dictionary_write(len(sorted_words), "json", str(path))
    return True


# --- Chrome (checksum_v1) ---


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
    except PermissionError, OSError:
        _warn_write_failed(path, quiet=quiet)
        return False
    if not _is_quiet(quiet):
        log.dictionary_write(len(sorted_words), "chrome", str(path))
    return True


# --- JetBrains (cachedDictionary.xml / spellchecker-dictionary.xml) ---


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


def _jetbrains_component_name(path: PathLike) -> str:
    target = Path(path)
    if not target.exists():
        return "CachedDictionaryState"
    try:
        text = target.read_text(encoding="utf-8", errors="ignore")
    except PermissionError, OSError:
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
    ET.indent(root, space="  ")
    xml_body = ET.tostring(root, encoding="unicode")
    payload = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_body + "\n"
    try:
        atomic_write(path, payload.encode("utf-8"))
    except PermissionError, OSError:
        _warn_write_failed(path, quiet=quiet)
        return False
    if not _is_quiet(quiet):
        log.dictionary_write(len(sorted_words), "jetbrains", str(path))
    return True
