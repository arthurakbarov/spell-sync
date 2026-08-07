"""Transactional push: durable recovery snapshots and rollback on error."""

from __future__ import annotations

import shutil
import tempfile
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List

from .dictionaries import Dictionary
from .io import create_bak_backup, is_path_readable, physical_path
from .log import log
from .project import ProjectContext
from .secure_artifacts import (
    SecureArtifactError,
    copy_trusted_snapshot_file,
    prepare_trusted_txn_root,
    remove_trusted_tree,
    trusted_project_root,
)


class TargetWriteState(str, Enum):
    NOT_STARTED = "not_started"
    WRITE_STARTED = "write_started"
    WRITE_COMPLETED = "write_completed"
    ROLLBACK_COMPLETED = "rollback_completed"
    ROLLBACK_FAILED = "rollback_failed"


@dataclass(frozen=True)
class RollbackResult:
    restored: tuple[str, ...]
    failed: tuple[str, ...]
    conflicts: tuple[str, ...]


@dataclass
class _FileBackup:
    path: Path
    backup: Path | None  # durable recovery snapshot path
    existed_before: bool
    label: str
    write_state: TargetWriteState = TargetWriteState.NOT_STARTED


def _file_existed(path: Path) -> bool:
    return physical_path(path).is_file()


def txn_snapshot_root(wordlist: Path, transaction_id: str) -> Path:
    """Persistent snapshot directory beside the wordlist (survives process crash)."""
    return ProjectContext.build(wordlist).project_dir / ".spell-sync.txn" / transaction_id


def _recovery_snapshot(path: Path, snapshot_dir: Path, *, root: Path, label: str) -> _FileBackup:
    existed_before = _file_existed(path)
    if not existed_before:
        return _FileBackup(path, None, False, label)
    target = physical_path(path)
    if not is_path_readable(target):
        log.warn(f"backup skipped {path}: read failed (path permissions)")
        return _FileBackup(path, None, True, label)
    try:
        snap = copy_trusted_snapshot_file(
            snapshot_dir,
            root=root,
            base_name=target.name,
            source=target,
        )
    except OSError, SecureArtifactError:
        log.warn(f"backup skipped {path}: recovery snapshot not created")
        return _FileBackup(path, None, True, label)
    create_bak_backup(target)
    return _FileBackup(path, snap, True, label)


def _plan_backup_path(path: Path, temp_dir: Path, *, label: str = "plan") -> _FileBackup:
    existed_before = _file_existed(path)
    if not existed_before:
        return _FileBackup(path, None, False, label)
    target = physical_path(path)
    if not is_path_readable(target):
        log.warn(f"backup skipped {path}: read failed (path permissions)")
        return _FileBackup(path, None, True, label)
    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
        tmp_target = temp_dir / f"{target.name}.plan"
        shutil.copy2(target, tmp_target)
    except OSError:
        log.warn(f"backup skipped {path}: temp backup not created")
        return _FileBackup(path, None, True, label)
    return _FileBackup(path, tmp_target, True, label)


def _artifact_root(backup_dir: Path, root: Path | None) -> Path:
    if root is not None:
        return root
    if backup_dir.parent.name == ".spell-sync.txn":
        return backup_dir.parent.parent
    return backup_dir.parent


def backup_file(
    path: Path,
    backup_dir: Path,
    *,
    root: Path | None = None,
    label: str = "wordlist",
) -> _FileBackup:
    return _recovery_snapshot(path, backup_dir, root=_artifact_root(backup_dir, root), label=label)


def backup_dictionaries(
    dictionaries: List[Dictionary],
    backup_dir: Path,
    *,
    root: Path | None = None,
) -> List[_FileBackup]:
    effective_root = _artifact_root(backup_dir, root)
    return [
        _recovery_snapshot(Path(d.path), backup_dir, root=effective_root, label=d.name)
        for d in dictionaries
    ]


def dictionaries_ready_to_write(
    dictionaries: List[Dictionary],
    backups: List[_FileBackup],
) -> List[Dictionary]:
    ready: List[Dictionary] = []
    for dictionary, bak in zip(dictionaries, backups):
        if bak.existed_before and bak.backup is None:
            continue
        ready.append(dictionary)
    return ready


def _rollback_one_backup(bak: _FileBackup) -> bool:
    if bak.write_state is TargetWriteState.NOT_STARTED:
        return True
    target = physical_path(bak.path)
    try:
        if bak.backup is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bak.backup, target)
            bak.write_state = TargetWriteState.ROLLBACK_COMPLETED
            return True
        if bak.existed_before:
            log.warn(f"rollback skipped {bak.path} — no snapshot was made, file left unchanged")
            bak.write_state = TargetWriteState.ROLLBACK_FAILED
            return False
        if target.is_file():
            target.unlink()
            bak.write_state = TargetWriteState.ROLLBACK_COMPLETED
            return True
        bak.write_state = TargetWriteState.ROLLBACK_COMPLETED
        return True
    except OSError as exc:
        log.warn(f"rollback failed {bak.path}: {exc}")
        bak.write_state = TargetWriteState.ROLLBACK_FAILED
        return False


def rollback_backups(backups: List[_FileBackup]) -> RollbackResult:
    restored: list[str] = []
    failed: list[str] = []
    for bak in backups:
        if bak.write_state is TargetWriteState.NOT_STARTED:
            continue
        if _rollback_one_backup(bak):
            if bak.write_state is TargetWriteState.ROLLBACK_COMPLETED:
                restored.append(bak.label)
        else:
            failed.append(bak.label)
    return RollbackResult(tuple(restored), tuple(failed), ())


def discard_txn_snapshots(
    snapshot_dir: Path | None,
    *,
    wordlist: Path | None = None,
    transaction_id: str | None = None,
) -> None:
    del transaction_id  # retained for call-site compatibility
    if snapshot_dir is None or wordlist is None:
        return
    root = trusted_project_root(wordlist)
    try:
        remove_trusted_tree(snapshot_dir, root=root)
        parent = snapshot_dir.parent
        if parent.name == ".spell-sync.txn" and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
    except SecureArtifactError, OSError:
        pass


@dataclass
class PushTransaction:
    """Durable recovery snapshots + rollback context for push."""

    dictionary_backups: List[_FileBackup]
    wordlist_backup: _FileBackup
    transaction_id: str
    snapshot_dir: Path | None
    wordlist_path: Path
    keep_dictionary_backup: bool = True
    _plan_tmpdir: tempfile.TemporaryDirectory[str] | None = None

    @classmethod
    def begin(
        cls,
        wordlist: Path,
        dictionaries: List[Dictionary],
        *,
        dry_run: bool = False,
    ) -> PushTransaction:
        transaction_id = str(uuid.uuid4())
        if dry_run:
            tmp = tempfile.TemporaryDirectory(prefix="spell-sync-plan-")
            root = Path(tmp.name)
            return cls(
                dictionary_backups=[
                    _plan_backup_path(Path(d.path), root, label=d.name) for d in dictionaries
                ],
                wordlist_backup=_plan_backup_path(wordlist, root, label="wordlist"),
                transaction_id=transaction_id,
                snapshot_dir=None,
                wordlist_path=wordlist,
                keep_dictionary_backup=True,
                _plan_tmpdir=tmp,
            )
        root = trusted_project_root(wordlist)
        try:
            snapshot_dir = prepare_trusted_txn_root(wordlist, transaction_id)
        except SecureArtifactError as exc:
            raise OSError(exc.detail) from exc
        return cls(
            dictionary_backups=backup_dictionaries(dictionaries, snapshot_dir, root=root),
            wordlist_backup=backup_file(wordlist, snapshot_dir, root=root, label="wordlist"),
            transaction_id=transaction_id,
            snapshot_dir=snapshot_dir,
            wordlist_path=wordlist,
            keep_dictionary_backup=False,
            _plan_tmpdir=None,
        )

    def backup_for_dictionary(self, dictionary: Dictionary) -> _FileBackup | None:
        path = Path(dictionary.path)
        for bak in self.dictionary_backups:
            if bak.path == path:
                return bak
        return None

    def mark_write_started(self, dictionary: Dictionary) -> None:
        bak = self.backup_for_dictionary(dictionary)
        if bak is not None:
            bak.write_state = TargetWriteState.WRITE_STARTED

    def mark_write_completed(self, dictionary: Dictionary) -> None:
        bak = self.backup_for_dictionary(dictionary)
        if bak is not None:
            bak.write_state = TargetWriteState.WRITE_COMPLETED

    def mark_wordlist_write_started(self) -> None:
        self.wordlist_backup.write_state = TargetWriteState.WRITE_STARTED

    def mark_wordlist_write_completed(self) -> None:
        self.wordlist_backup.write_state = TargetWriteState.WRITE_COMPLETED

    def rollback(self) -> RollbackResult:
        dict_result = rollback_backups(self.dictionary_backups)
        wordlist_result = rollback_backups([self.wordlist_backup])
        restored = dict_result.restored + wordlist_result.restored
        failed = dict_result.failed + wordlist_result.failed
        result = RollbackResult(restored, failed, ())
        if result.restored and not result.failed:
            log.warn("push rolled back — restored previous dictionary and wordlist versions.")
        elif result.restored:
            log.warn(
                "push rollback incomplete — restored: "
                f"{', '.join(result.restored)}; failed: {', '.join(result.failed)}"
            )
        elif result.failed:
            log.warn(f"push rollback failed for: {', '.join(result.failed)}")
        return result

    def discard_snapshots(self) -> None:
        discard_txn_snapshots(
            self.snapshot_dir,
            wordlist=self.wordlist_path,
            transaction_id=self.transaction_id,
        )
        self.snapshot_dir = None

    def close(self) -> None:
        if self._plan_tmpdir is not None:
            self._plan_tmpdir.cleanup()
