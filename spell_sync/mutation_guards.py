"""Shared lock and validation guards for commands that change files."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .exit_codes import ExitCode
from .guest_messages import (
    LOCK_PATH_UNSAFE,
    config_blocks_mutation_message,
    mutation_aborted_corrupt_journal_message,
    mutation_aborted_journal_message,
    mutation_aborted_unsafe_journal_message,
)
from .json_output import base_payload, emit_json
from .log import log
from .operation_lock import (
    OperationLocked,
    OperationLockRejected,
    acquire_operation_lock,
    lock_info_payload,
)
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
                    "detail": exc.code,
                }
            )
        else:
            log.abort(LOCK_PATH_UNSAFE)
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
                "Inspect `.spell-sync.lock` in the project directory."
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
        log.abort(config_blocks_mutation_message(result.status.value))
    return int(ExitCode.PUSH_ABORT)


def unfinished_journal_exit_from_result_for(
    command: str,
    result: JournalLoadResult,
    *,
    json_output: bool = False,
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
        JournalLoadStatus.UNSAFE_ARTIFACT,
    ):
        reason = (
            "unsafe_journal_artifact"
            if result.status is JournalLoadStatus.UNSAFE_ARTIFACT
            else "corrupt_journal"
        )
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
            if result.status is JournalLoadStatus.UNSAFE_ARTIFACT:
                log.abort(mutation_aborted_unsafe_journal_message(detail))
            else:
                log.abort(mutation_aborted_corrupt_journal_message(detail))
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
        log.abort(mutation_aborted_journal_message(journal.started, journal.pid))
    return int(ExitCode.PUSH_ABORT)
