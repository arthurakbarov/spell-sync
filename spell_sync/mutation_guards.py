"""Shared lock and validation guards for mutating commands."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .exit_codes import ExitCode
from .json_output import base_payload, emit_json
from .log import log
from .operation_lock import (
    OperationLocked,
    OperationLockRejected,
    acquire_operation_lock,
    lock_info_payload,
)
from .paths import wordlist_path
from .push_journal import JournalLoadResult, JournalLoadStatus, journal_payload
from .settings import config_blocks_mutating


@contextmanager
def operation_lock_scope_for(
    wordlist: Path,
    command: str,
    *,
    json_output: bool = False,
) -> Iterator[int | None]:
    try:
        with acquire_operation_lock(wordlist, command):
            yield None
    except OperationLockRejected as exc:
        if json_output:
            emit_json(
                {
                    **base_payload(command, exit=int(ExitCode.PUSH_ABORT)),
                    "reason": "unsafe_operation_lock",
                    "detail": exc.detail,
                }
            )
        else:
            log.abort(
                "operation aborted — project lock path is unsafe "
                f"({exc.detail}). Inspect `.spell-sync.lock` in the project directory."
            )
        yield int(ExitCode.PUSH_ABORT)
    except OperationLocked as exc:
        if json_output:
            emit_json(
                {
                    **base_payload(command, exit=int(ExitCode.PUSH_ABORT)),
                    "reason": "operation_locked",
                    "lock": lock_info_payload(exc.info),
                }
            )
        else:
            log.abort(
                "operation aborted — another spell-sync process is running "
                f"({exc.info.command}, pid {exc.info.pid}). "
                f"Lock file: {exc.lock_path}"
            )
        yield int(ExitCode.PUSH_ABORT)


def invalid_config_exit_from_scope(
    command: str,
    result,
    *,
    json_output: bool = False,
) -> int | None:
    if not config_blocks_mutating(result):
        return None
    diagnostics = [
        {"path": item.path, "message": item.message, "kind": item.kind.value}
        for item in result.diagnostics
    ]
    if json_output:
        emit_json(
            {
                **base_payload(command, exit=int(ExitCode.PUSH_ABORT)),
                "reason": "invalid_config",
                "config_status": result.status.value,
                "diagnostics": diagnostics,
            }
        )
    else:
        log.abort(
            "operation aborted — invalid spell-sync.toml "
            f"({result.status.value}). Fix config before mutating commands."
        )
    return int(ExitCode.PUSH_ABORT)


def unfinished_journal_exit_from_result_for(
    command: str,
    result: JournalLoadResult,
    *,
    json_output: bool = False,
    wordlist: Path | None = None,
) -> int | None:
    if command == "recover":
        return None
    if result.status is JournalLoadStatus.ABSENT:
        return None
    if result.status is JournalLoadStatus.VALID_COMPLETED:
        return None
    if result.status in (
        JournalLoadStatus.CORRUPT,
        JournalLoadStatus.UNSUPPORTED_SCHEMA,
    ):
        reason = "corrupt_journal"
        detail = result.detail or result.status.value
        if json_output:
            emit_json(
                {
                    **base_payload(command, exit=int(ExitCode.PUSH_ABORT)),
                    "reason": reason,
                    "detail": detail,
                }
            )
        else:
            wl = wordlist if wordlist is not None else wordlist_path()
            log.abort(
                "operation aborted — push journal is corrupt or unsupported "
                f"({detail}). Inspect or remove "
                f"{wl.resolve().parent / '.spell-sync.journal.json'} carefully."
            )
        return int(ExitCode.PUSH_ABORT)
    journal = result.journal
    assert journal is not None
    if json_output:
        emit_json(
            {
                **base_payload(command, exit=int(ExitCode.PUSH_ABORT)),
                "reason": "unfinished_transaction",
                "journal": journal_payload(journal),
            }
        )
    else:
        log.abort(
            "operation aborted — unfinished push journal found "
            f"({journal.started}, pid {journal.pid}). "
            "Run `spell-sync recover` before mutating commands."
        )
    return int(ExitCode.PUSH_ABORT)
