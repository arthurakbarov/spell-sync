"""Persistent push journal for crash recovery."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from .dictionaries import Dictionary
from .io import physical_path
from .journal_schema import (
    _KNOWN_COMMANDS,
    JournalParseError,
    parse_journal_target,
    parse_non_empty_str,
    parse_positive_int,
    parse_transaction_id,
    parse_wordlist_state,
    validate_journal_provenance,
)
from .log import log
from .project import ProjectContext
from .push_transaction import PushTransaction, txn_snapshot_root
from .secure_artifacts import (
    SecureArtifactError,
    atomic_write_trusted_file,
    read_trusted_regular_file,
    remove_empty_trusted_directory,
    remove_trusted_file,
    remove_trusted_tree,
    trusted_project_root,
)

JOURNAL_SCHEMA_VERSION = 2
SUPPORTED_SCHEMA_VERSIONS = frozenset({2})

JOURNAL_STATE_WRITING = "writing"
JOURNAL_STATE_COMPLETED = "completed"
JOURNAL_STATE_ROLLBACK_INCOMPLETE = "rollback_incomplete"


class JournalLoadStatus(str, Enum):
    ABSENT = "absent"
    VALID_IN_PROGRESS = "valid_in_progress"
    VALID_COMPLETED = "valid_completed"
    CORRUPT = "corrupt"
    UNSUPPORTED_SCHEMA = "unsupported_schema"
    UNSAFE_ARTIFACT = "unsafe_artifact"


@dataclass(frozen=True)
class JournalTarget:
    name: str
    path: str
    hash_before: str | None
    hash_after: str | None
    backup_path: str | None
    existed_before: bool = True
    write_started: bool = False
    write_completed: bool = False


@dataclass
class PushJournal:
    schema_version: int
    transaction_id: str
    command: str
    pid: int
    started: str
    state: str
    wordlist: str
    wordlist_hash_before: str | None
    wordlist_hash_after: str | None
    wordlist_backup_path: str | None
    wordlist_existed_before: bool = True
    wordlist_write_started: bool = False
    wordlist_write_completed: bool = False
    snapshot_dir: str | None = None
    targets: list[JournalTarget] = field(default_factory=list)


@dataclass(frozen=True)
class JournalLoadResult:
    status: JournalLoadStatus
    journal: PushJournal | None
    detail: str | None = None
    content_digest: str | None = None


@dataclass(frozen=True)
class RecoverResult:
    restored: tuple[str, ...]
    skipped: tuple[str, ...]
    failed: tuple[str, ...]
    conflicts: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecoveryItemPlan:
    name: str
    path: str
    current_state: str
    recovery_action: str
    status: str
    detail: str | None
    existed_before: bool
    write_started: bool
    write_completed: bool
    snapshot_valid: bool


def _snapshot_is_valid(backup: Path | None, hash_before: str | None) -> bool:
    if backup is None or not backup.is_file():
        return False
    if backup.is_symlink():
        return False
    if hash_before is None:
        return True
    return file_content_hash(backup) == hash_before


def _plan_recovery_item(
    label: str,
    target: Path,
    backup: Path | None,
    *,
    existed_before: bool,
    hash_before: str | None,
    hash_after: str | None,
    write_started: bool,
    write_completed: bool,
) -> RecoveryItemPlan:
    destination = physical_path(target)
    snapshot_valid = _snapshot_is_valid(backup, hash_before)
    if not write_started and not write_completed:
        return RecoveryItemPlan(
            name=label,
            path=str(destination),
            current_state="Unchanged",
            recovery_action="No action",
            status="skipped",
            detail="Write never started",
            existed_before=existed_before,
            write_started=write_started,
            write_completed=write_completed,
            snapshot_valid=snapshot_valid,
        )
    if not existed_before:
        if not destination.is_file():
            return RecoveryItemPlan(
                name=label,
                path=str(destination),
                current_state="Missing",
                recovery_action="No action",
                status="skipped",
                detail="Target was not created",
                existed_before=False,
                write_started=write_started,
                write_completed=write_completed,
                snapshot_valid=snapshot_valid,
            )
        current = file_content_hash(destination)
        if hash_after is None or current != hash_after:
            return RecoveryItemPlan(
                name=label,
                path=str(destination),
                current_state="External change",
                recovery_action="No automatic write",
                status="conflict",
                detail="File differs from transaction hash_after",
                existed_before=False,
                write_started=write_started,
                write_completed=write_completed,
                snapshot_valid=snapshot_valid,
            )
        return RecoveryItemPlan(
            name=label,
            path=str(destination),
            current_state="Post-write",
            recovery_action="Remove created file",
            status="ready" if snapshot_valid else "failed",
            detail=None if snapshot_valid else "Snapshot invalid",
            existed_before=False,
            write_started=write_started,
            write_completed=write_completed,
            snapshot_valid=snapshot_valid,
        )
    if backup is None or not Path(backup).is_file():
        return RecoveryItemPlan(
            name=label,
            path=str(destination),
            current_state="Post-write" if destination.is_file() else "Missing",
            recovery_action="Restore snapshot",
            status="failed",
            detail="Snapshot missing",
            existed_before=True,
            write_started=write_started,
            write_completed=write_completed,
            snapshot_valid=False,
        )
    if not snapshot_valid:
        return RecoveryItemPlan(
            name=label,
            path=str(destination),
            current_state="Post-write" if destination.is_file() else "Missing",
            recovery_action="Restore snapshot",
            status="failed",
            detail="Snapshot hash mismatch",
            existed_before=True,
            write_started=write_started,
            write_completed=write_completed,
            snapshot_valid=False,
        )
    current = file_content_hash(destination) if destination.is_file() else None
    if current == hash_before:
        return RecoveryItemPlan(
            name=label,
            path=str(destination),
            current_state="Original",
            recovery_action="Already restored",
            status="skipped",
            detail=None,
            existed_before=True,
            write_started=write_started,
            write_completed=write_completed,
            snapshot_valid=True,
        )
    if current == hash_after:
        current_state = "Post-write"
    elif not destination.is_file():
        current_state = "Missing"
    else:
        return RecoveryItemPlan(
            name=label,
            path=str(destination),
            current_state="External change",
            recovery_action="No automatic write",
            status="conflict",
            detail="File changed outside spell-sync",
            existed_before=True,
            write_started=write_started,
            write_completed=write_completed,
            snapshot_valid=True,
        )
    return RecoveryItemPlan(
        name=label,
        path=str(destination),
        current_state=current_state,
        recovery_action="Restore snapshot",
        status="ready",
        detail=None,
        existed_before=True,
        write_started=write_started,
        write_completed=write_completed,
        snapshot_valid=True,
    )


def plan_recovery_from_journal(journal: PushJournal) -> tuple[RecoveryItemPlan, ...]:
    items: list[RecoveryItemPlan] = []
    wordlist = Path(journal.wordlist)
    items.append(
        _plan_recovery_item(
            "wordlist",
            wordlist,
            Path(journal.wordlist_backup_path) if journal.wordlist_backup_path else None,
            existed_before=journal.wordlist_existed_before,
            hash_before=journal.wordlist_hash_before,
            hash_after=journal.wordlist_hash_after,
            write_started=journal.wordlist_write_started,
            write_completed=journal.wordlist_write_completed,
        )
    )
    for target in journal.targets:
        items.append(
            _plan_recovery_item(
                target.name,
                Path(target.path),
                Path(target.backup_path) if target.backup_path else None,
                existed_before=target.existed_before,
                hash_before=target.hash_before,
                hash_after=target.hash_after,
                write_started=target.write_started,
                write_completed=target.write_completed,
            )
        )
    return tuple(items)


def journal_path_for_wordlist(wordlist: Path) -> Path:
    return ProjectContext.build(wordlist).project_dir / ".spell-sync.journal.json"


def file_content_hash(path: Path) -> str | None:
    target = physical_path(path)
    if not target.is_file():
        return None
    digest = hashlib.sha256()
    try:
        with open(target, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _secure_file_mode(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def journal_payload(journal: PushJournal) -> dict[str, object]:
    data = asdict(journal)
    data["targets"] = [asdict(target) for target in journal.targets]
    return data


def _parse_journal_dict(
    raw: dict[str, object],
    *,
    expected_wordlist: Path | None = None,
) -> PushJournal:
    schema_version = parse_positive_int(raw.get("schema_version"), field="schema_version")
    state = parse_non_empty_str(raw.get("state"), field="state")
    if state not in (
        JOURNAL_STATE_WRITING,
        JOURNAL_STATE_COMPLETED,
        JOURNAL_STATE_ROLLBACK_INCOMPLETE,
    ):
        raise JournalParseError(f"unknown state {state!r}")
    command = parse_non_empty_str(raw.get("command"), field="command")
    if command not in _KNOWN_COMMANDS:
        raise JournalParseError(f"unknown command {command!r}")
    transaction_id = parse_transaction_id(raw.get("transaction_id"))
    pid = parse_positive_int(raw.get("pid"), field="pid")
    started = parse_non_empty_str(raw.get("started"), field="started")
    wordlist = parse_non_empty_str(raw.get("wordlist"), field="wordlist")
    targets_raw = raw.get("targets", [])
    if not isinstance(targets_raw, list):
        raise JournalParseError("targets must be list")
    target_dicts: list[dict[str, object]] = []
    for item in targets_raw:
        if not isinstance(item, dict):
            raise JournalParseError("target must be object")
        target_dicts.append(parse_journal_target(item))
    wl_state = parse_wordlist_state(raw)
    snapshot_dir = raw.get("snapshot_dir")
    if snapshot_dir is not None and not isinstance(snapshot_dir, str):
        raise JournalParseError("snapshot_dir must be string or null")
    require_snapshots = state != JOURNAL_STATE_COMPLETED
    validate_journal_provenance(
        wordlist=wordlist,
        transaction_id=transaction_id,
        snapshot_dir=snapshot_dir,
        targets=target_dicts,
        wordlist_backup_path=wl_state["backup_path"],
        expected_wordlist=expected_wordlist,
        require_snapshots=require_snapshots,
    )
    targets = [
        JournalTarget(
            name=str(t["name"]),
            path=str(t["path"]),
            hash_before=t["hash_before"],  # type: ignore[arg-type]
            hash_after=t["hash_after"],  # type: ignore[arg-type]
            backup_path=t["backup_path"],  # type: ignore[arg-type]
            existed_before=bool(t["existed_before"]),
            write_started=bool(t["write_started"]),
            write_completed=bool(t["write_completed"]),
        )
        for t in target_dicts
    ]
    for target in targets:
        if (
            require_snapshots
            and target.existed_before
            and target.write_started
            and target.backup_path
        ):
            snap = Path(target.backup_path)
            if target.hash_before and file_content_hash(snap) != target.hash_before:
                raise JournalParseError(f"snapshot hash mismatch for {target.name}")
    if wl_state["existed_before"] and wl_state["write_started"] and wl_state["backup_path"]:
        if require_snapshots:
            snap = Path(wl_state["backup_path"])
            hb = wl_state["hash_before"]
            if hb and file_content_hash(snap) != hb:
                raise JournalParseError("wordlist snapshot hash mismatch")
    return PushJournal(
        schema_version=schema_version,
        transaction_id=transaction_id,
        command=command,
        pid=pid,
        started=started,
        state=state,
        wordlist=wordlist,
        wordlist_hash_before=wl_state["hash_before"],  # type: ignore[arg-type]
        wordlist_hash_after=wl_state["hash_after"],  # type: ignore[arg-type]
        wordlist_backup_path=wl_state["backup_path"],  # type: ignore[arg-type]
        wordlist_existed_before=bool(wl_state["existed_before"]),
        wordlist_write_started=bool(wl_state["write_started"]),
        wordlist_write_completed=bool(wl_state["write_completed"]),
        snapshot_dir=snapshot_dir,  # type: ignore[arg-type]
        targets=targets,
    )


def load_journal_result(
    wordlist: Path,
    *,
    validate_wordlist: bool = False,
) -> JournalLoadResult:
    path = journal_path_for_wordlist(wordlist)
    if not path.parent.exists():
        # Setup may run before the project directory exists; no journal can be present.
        return JournalLoadResult(JournalLoadStatus.ABSENT, None)
    root = trusted_project_root(wordlist)
    try:
        raw_bytes = read_trusted_regular_file(path, root=root)
    except SecureArtifactError as exc:
        if exc.code == "missing_file":
            return JournalLoadResult(JournalLoadStatus.ABSENT, None)
        return JournalLoadResult(JournalLoadStatus.UNSAFE_ARTIFACT, None, exc.detail)
    except OSError as exc:
        return JournalLoadResult(JournalLoadStatus.CORRUPT, None, str(exc))
    content_digest = hashlib.sha256(raw_bytes).hexdigest()
    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (json.JSONDecodeError, TypeError, ValueError, UnicodeDecodeError) as exc:
        return JournalLoadResult(
            JournalLoadStatus.CORRUPT, None, str(exc), content_digest=content_digest
        )
    if not isinstance(raw, dict):
        return JournalLoadResult(
            JournalLoadStatus.CORRUPT,
            None,
            "journal root must be object",
            content_digest=content_digest,
        )
    schema = raw.get("schema_version")
    if schema not in SUPPORTED_SCHEMA_VERSIONS:
        return JournalLoadResult(
            JournalLoadStatus.UNSUPPORTED_SCHEMA,
            None,
            f"unsupported schema_version={schema!r}",
            content_digest=content_digest,
        )
    try:
        expected = wordlist if validate_wordlist else None
        journal = _parse_journal_dict(raw, expected_wordlist=expected)
    except JournalParseError as exc:
        return JournalLoadResult(
            JournalLoadStatus.CORRUPT, None, str(exc), content_digest=content_digest
        )

    if journal.state == JOURNAL_STATE_COMPLETED:
        return JournalLoadResult(
            JournalLoadStatus.VALID_COMPLETED, journal, content_digest=content_digest
        )
    return JournalLoadResult(
        JournalLoadStatus.VALID_IN_PROGRESS, journal, content_digest=content_digest
    )


def load_push_journal(wordlist: Path) -> PushJournal | None:
    """Return in-progress journal, or None if absent/completed/corrupt."""
    result = load_journal_result(wordlist)
    if result.status is JournalLoadStatus.VALID_IN_PROGRESS:
        return result.journal
    return None


def _atomic_write_journal(path: Path, journal: PushJournal, *, wordlist: Path) -> None:
    payload = json.dumps(journal_payload(journal), ensure_ascii=False, indent=2) + "\n"
    root = trusted_project_root(wordlist)
    try:
        atomic_write_trusted_file(path, payload.encode("utf-8"), root=root)
    except SecureArtifactError as exc:
        raise OSError(exc.detail) from exc


def _backup_path_string(backup: Path | None) -> str | None:
    if backup is None:
        return None
    return str(backup)


def _journal_from_transaction(
    wordlist: Path,
    *,
    command: str,
    tx: PushTransaction,
    dictionaries: list[Dictionary],
) -> PushJournal:
    backup_by_path = {bak.path: bak for bak in tx.dictionary_backups}
    targets: list[JournalTarget] = []
    for dictionary in dictionaries:
        path = Path(dictionary.path)
        bak = backup_by_path.get(path)
        backup = bak.backup if bak is not None else None
        existed = bak.existed_before if bak is not None else path.is_file()
        targets.append(
            JournalTarget(
                name=dictionary.name,
                path=str(path.resolve()),
                hash_before=file_content_hash(path),
                hash_after=None,
                backup_path=_backup_path_string(backup),
                existed_before=existed,
            )
        )
    wordlist_backup = tx.wordlist_backup.backup
    return PushJournal(
        schema_version=JOURNAL_SCHEMA_VERSION,
        transaction_id=tx.transaction_id,
        command=command,
        pid=os.getpid(),
        started=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        state=JOURNAL_STATE_WRITING,
        wordlist=str(wordlist.resolve()),
        wordlist_hash_before=file_content_hash(wordlist),
        wordlist_hash_after=None,
        wordlist_backup_path=_backup_path_string(wordlist_backup),
        wordlist_existed_before=tx.wordlist_backup.existed_before,
        snapshot_dir=str(tx.snapshot_dir) if tx.snapshot_dir is not None else None,
        targets=targets,
    )


class PushJournalSession:
    """Track in-progress push state on disk until COMPLETED or discard."""

    def __init__(self, path: Path, journal: PushJournal, *, wordlist: Path) -> None:
        self._path = path
        self._journal = journal
        self._wordlist = wordlist
        _atomic_write_journal(path, journal, wordlist=wordlist)

    @classmethod
    def begin(
        cls,
        wordlist: Path,
        *,
        command: str,
        tx: PushTransaction,
        dictionaries: list[Dictionary],
    ) -> PushJournalSession:
        path = journal_path_for_wordlist(wordlist)
        journal = _journal_from_transaction(
            wordlist,
            command=command,
            tx=tx,
            dictionaries=dictionaries,
        )
        return cls(path, journal, wordlist=wordlist)

    @property
    def journal(self) -> PushJournal:
        return self._journal

    def _persist(self) -> None:
        _atomic_write_journal(self._path, self._journal, wordlist=self._wordlist)

    def mark_wordlist_write_started(self, hash_after: str) -> None:
        self._journal.wordlist_write_started = True
        self._journal.wordlist_hash_after = hash_after
        self._persist()

    def mark_wordlist_write_completed(self) -> None:
        self._journal.wordlist_write_completed = True
        self._persist()

    def mark_write_started(self, name: str, hash_after: str) -> None:
        for index, target in enumerate(self._journal.targets):
            if target.name == name:
                self._journal.targets[index] = replace(
                    target,
                    write_started=True,
                    write_completed=False,
                    hash_after=hash_after,
                )
                break
        self._persist()

    def mark_target_written(self, name: str) -> None:
        for index, target in enumerate(self._journal.targets):
            if target.name == name:
                path = Path(target.path)
                actual = file_content_hash(path)
                if target.hash_after is not None and actual != target.hash_after:
                    raise OSError(f"post-write hash mismatch for {name}")
                self._journal.targets[index] = replace(
                    target,
                    write_started=True,
                    write_completed=True,
                )
                break
        self._persist()

    def mark_rollback_incomplete(self) -> None:
        self._journal.state = JOURNAL_STATE_ROLLBACK_INCOMPLETE
        self._persist()

    def complete(self) -> None:
        """Mark COMPLETED durably, then best-effort remove the journal file."""
        self._journal.state = JOURNAL_STATE_COMPLETED
        _atomic_write_journal(self._path, self._journal, wordlist=self._wordlist)
        try:
            remove_trusted_file(self._path, root=trusted_project_root(self._wordlist))
        except (SecureArtifactError, OSError) as exc:
            log.warn(f"journal cleanup warning — completed journal left on disk: {exc}")

    def discard(self) -> None:
        try:
            remove_trusted_file(self._path, root=trusted_project_root(self._wordlist))
        except SecureArtifactError, OSError:
            pass


def recover_from_journal(journal: PushJournal, *, dry_run: bool = False) -> RecoverResult:
    """Restore wordlist and targets from journal recovery snapshots."""
    restored: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    conflicts: list[str] = []

    def restore_one(
        label: str,
        target: Path,
        backup: Path | None,
        *,
        existed_before: bool,
        hash_before: str | None,
        hash_after: str | None,
        write_started: bool,
        write_completed: bool,
    ) -> None:
        destination = physical_path(target)
        if not write_started and not write_completed:
            skipped.append(label)
            return
        if not existed_before:
            if dry_run:
                restored.append(label)
                return
            if not destination.is_file():
                skipped.append(label)
                return
            current = file_content_hash(destination)
            if hash_after is None or current != hash_after:
                conflicts.append(label)
                return
            try:
                destination.unlink()
                restored.append(label)
            except OSError:
                failed.append(label)
            return
        if backup is None or not Path(backup).is_file():
            failed.append(label)
            return
        snap_hash = file_content_hash(Path(backup))
        if hash_before is not None and snap_hash != hash_before:
            failed.append(label)
            return
        current = file_content_hash(destination) if destination.is_file() else None
        if current == hash_before:
            skipped.append(label)
            return
        if current == hash_after:
            pass
        elif not destination.is_file():
            pass
        elif current is not None:
            conflicts.append(label)
            return
        if dry_run:
            restored.append(label)
            return
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Unique no-collision temp in the destination directory; never follow a
            # predictable recover-tmp symlink into another file.
            fd, temp_name = tempfile.mkstemp(
                prefix=destination.name + ".",
                suffix=".recover-tmp",
                dir=str(destination.parent),
            )
            os.close(fd)
            temp = Path(temp_name)
            try:
                shutil.copy2(backup, temp)
                with open(temp, "rb+") as handle:
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp, destination)
            except OSError:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
                raise
            restored.append(label)
        except OSError:
            failed.append(label)

    wordlist = Path(journal.wordlist)
    restore_one(
        "wordlist",
        wordlist,
        Path(journal.wordlist_backup_path) if journal.wordlist_backup_path else None,
        existed_before=journal.wordlist_existed_before,
        hash_before=journal.wordlist_hash_before,
        hash_after=journal.wordlist_hash_after,
        write_started=journal.wordlist_write_started,
        write_completed=journal.wordlist_write_completed,
    )

    for target in journal.targets:
        restore_one(
            target.name,
            Path(target.path),
            Path(target.backup_path) if target.backup_path else None,
            existed_before=target.existed_before,
            hash_before=target.hash_before,
            hash_after=target.hash_after,
            write_started=target.write_started,
            write_completed=target.write_completed,
        )

    return RecoverResult(
        tuple(restored),
        tuple(skipped),
        tuple(failed),
        tuple(conflicts),
    )


@dataclass(frozen=True)
class DiscardArtifactsResult:
    journal_removed: bool
    snapshots_removed: bool
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.detail is None


class DiscardSafetyError(ValueError):
    """Discard refused because recovery metadata paths are unsafe."""


def cleanup_after_successful_recovery(journal: PushJournal) -> DiscardArtifactsResult:
    """Remove journal and transaction snapshots after confirmed recovery."""
    wordlist = Path(journal.wordlist)
    snapshots_ok, snap_detail = safe_discard_txn_snapshots(
        wordlist,
        journal.transaction_id,
        journal.snapshot_dir,
    )
    if not snapshots_ok:
        return DiscardArtifactsResult(False, False, snap_detail)
    journal_ok, journal_detail = safe_discard_journal_file(wordlist)
    if not journal_ok:
        return DiscardArtifactsResult(False, True, journal_detail)
    return DiscardArtifactsResult(True, True, None)


def _safe_txn_snapshot_dir(
    wordlist: Path,
    transaction_id: str,
    snapshot_dir: str | None,
) -> Path | None:
    if not snapshot_dir:
        return None
    expected = txn_snapshot_root(wordlist, transaction_id)
    snap = Path(snapshot_dir)
    if snap.is_symlink():
        raise DiscardSafetyError("snapshot directory is a symlink")
    try:
        resolved = snap.resolve()
        expected_resolved = expected.resolve()
    except OSError as exc:
        raise DiscardSafetyError(str(exc)) from exc
    if resolved != expected_resolved:
        raise DiscardSafetyError("snapshot directory outside expected transaction directory")
    if not snap.is_dir():
        raise DiscardSafetyError("snapshot directory missing")
    return snap


def safe_discard_txn_snapshots(
    wordlist: Path,
    transaction_id: str,
    snapshot_dir: str | None,
) -> tuple[bool, str | None]:
    try:
        snap = _safe_txn_snapshot_dir(wordlist, transaction_id, snapshot_dir)
    except DiscardSafetyError as exc:
        return False, str(exc)
    if snap is None:
        return True, None
    root = trusted_project_root(wordlist)
    try:
        remove_trusted_tree(snap, root=root)
        txn_parent = snap.parent
        if txn_parent.name == ".spell-sync.txn":
            try:
                remove_empty_trusted_directory(txn_parent, root=root)
            except SecureArtifactError:
                pass
        return True, None
    except (SecureArtifactError, OSError) as exc:
        return False, str(exc)


def safe_discard_journal_file(wordlist: Path) -> tuple[bool, str | None]:
    path = journal_path_for_wordlist(wordlist)
    root = trusted_project_root(wordlist)
    try:
        remove_trusted_file(path, root=root)
        return True, None
    except SecureArtifactError as exc:
        return False, exc.detail or exc.code


def discard_txn_snapshots(
    snapshot_dir: Path | None,
    *,
    wordlist: Path | None = None,
) -> None:
    if snapshot_dir is None or wordlist is None:
        return
    root = trusted_project_root(wordlist)
    try:
        remove_trusted_tree(snapshot_dir, root=root)
        txn_parent = snapshot_dir.parent
        if txn_parent.name == ".spell-sync.txn":
            try:
                remove_empty_trusted_directory(txn_parent, root=root)
            except SecureArtifactError:
                pass
    except SecureArtifactError, OSError:
        pass


def discard_journal(wordlist: Path) -> None:
    ok, detail = safe_discard_journal_file(wordlist)
    if not ok:
        raise DiscardSafetyError(detail or "journal discard failed")


def discard_completed_journal(wordlist: Path) -> DiscardArtifactsResult:
    """Remove a completed leftover journal and orphan snapshots after successful cleanup."""
    result = load_journal_result(wordlist)
    if result.status is not JournalLoadStatus.VALID_COMPLETED or result.journal is None:
        return DiscardArtifactsResult(
            journal_removed=False,
            snapshots_removed=False,
            detail="completed journal is not present",
        )
    journal = result.journal
    snapshots_ok, snap_detail = safe_discard_txn_snapshots(
        wordlist,
        journal.transaction_id,
        journal.snapshot_dir,
    )
    if not snapshots_ok:
        return DiscardArtifactsResult(False, False, snap_detail)
    journal_ok, journal_detail = safe_discard_journal_file(wordlist)
    if not journal_ok:
        return DiscardArtifactsResult(False, snapshots_ok, journal_detail)
    return DiscardArtifactsResult(True, True, None)
