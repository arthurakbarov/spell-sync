"""Strict push journal JSON parsing and path validation."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from .push_transaction import txn_snapshot_root

_HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_KNOWN_COMMANDS = frozenset(
    {
        "pull",
        "push",
        "recover",
        "lint",
        "plan",
        "status",
    }
)
_KNOWN_STATES = frozenset({"writing", "completed", "rollback_incomplete"})
JOURNAL_SCHEMA_VERSION = 2


class JournalParseError(ValueError):
    """Invalid journal field."""


def parse_bool_field(value: Any, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    raise JournalParseError(f"{field} must be boolean, got {type(value).__name__}")


def parse_hash_field(value: Any, *, field: str, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise JournalParseError(f"{field} is required")
        return None
    if not isinstance(value, str):
        raise JournalParseError(f"{field} must be string or null")
    if not _HASH_RE.fullmatch(value):
        raise JournalParseError(f"{field} must be 64 hex chars")
    return value.lower()


def parse_positive_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise JournalParseError(f"{field} must be integer")
    if value <= 0:
        raise JournalParseError(f"{field} must be positive")
    return int(value)


def parse_non_empty_str(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise JournalParseError(f"{field} must be non-empty string")
    return value


def parse_transaction_id(value: Any) -> str:
    text = parse_non_empty_str(value, field="transaction_id")
    try:
        uuid.UUID(text)
    except ValueError as exc:
        raise JournalParseError("transaction_id must be UUID") from exc
    return text


def _path_inside(base: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _validate_target_path(path: str) -> None:
    if not path.strip():
        raise JournalParseError("target path empty")
    if ".." in Path(path).parts:
        raise JournalParseError(f"unsafe path {path}")


def parse_journal_target(item: dict[str, Any]) -> dict[str, Any]:
    name = parse_non_empty_str(item["name"], field="target.name")
    path = parse_non_empty_str(item["path"], field="target.path")
    _validate_target_path(path)
    hash_before = parse_hash_field(item.get("hash_before"), field="target.hash_before")
    hash_after = parse_hash_field(item.get("hash_after"), field="target.hash_after")
    backup_path = item.get("backup_path")
    if backup_path is not None and not isinstance(backup_path, str):
        raise JournalParseError("target.backup_path must be string or null")
    existed_before = parse_bool_field(
        item.get("existed_before", True),
        field="target.existed_before",
    )
    write_started = parse_bool_field(
        item.get("write_started", False),
        field="target.write_started",
    )
    write_completed = parse_bool_field(
        item.get("write_completed", False),
        field="target.write_completed",
    )
    if write_completed and not write_started:
        raise JournalParseError("write_completed requires write_started")
    if write_completed and hash_after is None:
        raise JournalParseError("completed target requires hash_after")
    if existed_before and write_started and hash_before is None:
        raise JournalParseError("existing target write requires hash_before")
    return {
        "name": name,
        "path": path,
        "hash_before": hash_before,
        "hash_after": hash_after,
        "backup_path": backup_path,
        "existed_before": existed_before,
        "write_started": write_started,
        "write_completed": write_completed,
    }


def parse_wordlist_state(raw: dict[str, Any]) -> dict[str, Any]:
    existed_before = parse_bool_field(
        raw.get("wordlist_existed_before", True),
        field="wordlist_existed_before",
    )
    hash_before = parse_hash_field(raw.get("wordlist_hash_before"), field="wordlist_hash_before")
    backup_path = raw.get("wordlist_backup_path")
    if backup_path is not None and not isinstance(backup_path, str):
        raise JournalParseError("wordlist_backup_path must be string or null")
    write_started = parse_bool_field(
        raw.get("wordlist_write_started", False),
        field="wordlist_write_started",
    )
    write_completed = parse_bool_field(
        raw.get("wordlist_write_completed", False),
        field="wordlist_write_completed",
    )
    hash_after = parse_hash_field(raw.get("wordlist_hash_after"), field="wordlist_hash_after")
    if write_completed and not write_started:
        raise JournalParseError("wordlist_write_completed requires wordlist_write_started")
    if write_completed and hash_after is None:
        raise JournalParseError("completed wordlist write requires wordlist_hash_after")
    if existed_before and write_started and hash_before is None:
        raise JournalParseError("existing wordlist write requires wordlist_hash_before")
    return {
        "existed_before": existed_before,
        "hash_before": hash_before,
        "hash_after": hash_after,
        "backup_path": backup_path,
        "write_started": write_started,
        "write_completed": write_completed,
    }


def validate_journal_provenance(
    *,
    wordlist: str,
    transaction_id: str,
    snapshot_dir: str | None,
    targets: list[dict[str, Any]],
    wordlist_backup_path: str | None,
    expected_wordlist: Path | None = None,
    require_snapshots: bool = True,
) -> None:
    if expected_wordlist is not None:
        if Path(wordlist).resolve() != expected_wordlist.resolve():
            raise JournalParseError("journal wordlist does not match command wordlist")
    parse_transaction_id(transaction_id)
    if ".." in Path(wordlist).parts:
        raise JournalParseError("unsafe wordlist path")
    if not snapshot_dir:
        if require_snapshots:
            raise JournalParseError("snapshot_dir required")
        return
    snap_root = txn_snapshot_root(Path(wordlist), transaction_id)
    snap_path = Path(snapshot_dir)
    if snap_path.resolve() != snap_root.resolve():
        raise JournalParseError("snapshot_dir outside transaction directory")
    if ".." in snap_path.parts:
        raise JournalParseError("unsafe snapshot_dir")
    if require_snapshots and not snap_path.is_dir():
        raise JournalParseError("snapshot_dir missing")
    names: set[str] = set()
    paths: set[str] = set()
    for target in targets:
        if target["name"] in names:
            raise JournalParseError(f"duplicate target name {target['name']!r}")
        names.add(target["name"])
        if target["path"] in paths:
            raise JournalParseError(f"duplicate target path {target['path']!r}")
        paths.add(target["path"])
    for label, backup in (
        ("wordlist", wordlist_backup_path),
        *((t["name"], t["backup_path"]) for t in targets),
    ):
        if backup is None:
            continue
        if not require_snapshots:
            continue
        bp = Path(backup)
        if bp.is_symlink():
            raise JournalParseError(f"{label} backup is symlink")
        if not bp.is_file():
            raise JournalParseError(f"{label} backup missing")
        if not _path_inside(snap_path, bp):
            raise JournalParseError(f"{label} backup outside snapshot_dir")
        if ".." in bp.parts:
            raise JournalParseError(f"{label} backup path unsafe")
