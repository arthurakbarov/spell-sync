"""Helpers for constructing valid push journals in tests."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from spell_sync.push_journal import (
    JOURNAL_SCHEMA_VERSION,
    JOURNAL_STATE_WRITING,
    JournalTarget,
    PushJournal,
    file_content_hash,
    journal_path_for_wordlist,
    journal_payload,
)
from spell_sync.push_transaction import txn_snapshot_root


def write_test_journal(
    wordlist: Path,
    *,
    command: str = "push",
    targets: list[JournalTarget] | None = None,
    wordlist_write_started: bool = False,
    wordlist_write_completed: bool = False,
    wordlist_hash_after: str | None = None,
    state: str = JOURNAL_STATE_WRITING,
) -> PushJournal:
    transaction_id = str(uuid.uuid4())
    snap = txn_snapshot_root(wordlist, transaction_id)
    snap.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if wordlist.is_file():
        backup = snap / "wordlist.snap"
        shutil.copy2(wordlist, backup)
    if wordlist_write_completed and wordlist_hash_after is None and wordlist.is_file():
        wordlist_hash_after = file_content_hash(wordlist)
    journal = PushJournal(
        schema_version=JOURNAL_SCHEMA_VERSION,
        transaction_id=transaction_id,
        command=command,
        pid=123,
        started="2026-01-01T00:00:00+00:00",
        state=state,
        wordlist=str(wordlist.resolve()),
        wordlist_hash_before=file_content_hash(wordlist),
        wordlist_hash_after=wordlist_hash_after,
        wordlist_backup_path=str(backup) if backup is not None else None,
        wordlist_existed_before=wordlist.is_file(),
        wordlist_write_started=wordlist_write_started,
        wordlist_write_completed=wordlist_write_completed,
        snapshot_dir=str(snap),
        targets=targets or [],
    )
    path = journal_path_for_wordlist(wordlist)
    path.write_text(json.dumps(journal_payload(journal), indent=2) + "\n", encoding="utf-8")
    return journal


def write_restore_scenario_journal(
    wordlist: Path,
    dict_path: Path,
    *,
    current_wordlist: str = "new\n",
    backup_wordlist: str = "old\n",
    current_dict: str = "new\n",
    backup_dict: str = "old\n",
) -> PushJournal:
    wordlist.write_text(current_wordlist, encoding="utf-8")
    dict_path.write_text(current_dict, encoding="utf-8")
    transaction_id = str(uuid.uuid4())
    snap = txn_snapshot_root(wordlist, transaction_id)
    snap.mkdir(parents=True, exist_ok=True)
    wl_backup = snap / "wordlist.snap"
    wl_backup.write_text(backup_wordlist, encoding="utf-8")
    dict_backup = snap / "dict.snap"
    dict_backup.write_text(backup_dict, encoding="utf-8")
    hash_before_wl = file_content_hash(wl_backup)
    hash_after_wl = file_content_hash(wordlist)
    hash_before_d = file_content_hash(dict_backup)
    hash_after_d = file_content_hash(dict_path)
    journal = PushJournal(
        schema_version=JOURNAL_SCHEMA_VERSION,
        transaction_id=transaction_id,
        command="push",
        pid=1,
        started="2026-01-01T00:00:00+00:00",
        state=JOURNAL_STATE_WRITING,
        wordlist=str(wordlist.resolve()),
        wordlist_hash_before=hash_before_wl,
        wordlist_hash_after=hash_after_wl,
        wordlist_backup_path=str(wl_backup),
        wordlist_write_started=True,
        wordlist_write_completed=True,
        snapshot_dir=str(snap),
        targets=[
            JournalTarget(
                name="d",
                path=str(dict_path.resolve()),
                hash_before=hash_before_d,
                hash_after=hash_after_d,
                backup_path=str(dict_backup),
                existed_before=True,
                write_started=True,
                write_completed=True,
            ),
        ],
    )
    journal_path_for_wordlist(wordlist).write_text(
        json.dumps(journal_payload(journal), indent=2) + "\n",
        encoding="utf-8",
    )
    return journal


def journal_target_from_file(
    name: str,
    path: Path,
    snap_dir: Path,
    *,
    write_started: bool = False,
    write_completed: bool = False,
    hash_after: str | None = None,
) -> JournalTarget:
    backup: Path | None = None
    existed = path.is_file()
    hash_before = file_content_hash(path) if existed else None
    if existed:
        backup = snap_dir / f"{name}.snap"
        shutil.copy2(path, backup)
    return JournalTarget(
        name=name,
        path=str(path.resolve()),
        hash_before=hash_before,
        hash_after=hash_after,
        backup_path=str(backup) if backup is not None else None,
        existed_before=existed,
        write_started=write_started,
        write_completed=write_completed,
    )
