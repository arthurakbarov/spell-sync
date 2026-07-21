"""Helpers for mocking SpellSyncService in CLI integration tests."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
from unittest.mock import MagicMock, patch

from spell_sync.application.reports import (
    DoctorTargetsSnapshot,
    DoctorTargetView,
    OperationOutcome,
    PullExecution,
    PullPreview,
    PushExecution,
    PushPreview,
    RecoveryExecution,
    RecoveryOutcome,
    RecoveryPreview,
    RecoveryStatus,
    StatusSnapshot,
)
from spell_sync.dictionaries import DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.push_journal import RecoverResult
from spell_sync.read_outcome import dictionary_read_result
from spell_sync.sync_run import DictionaryDiff, PushResult, SyncRun


def status_snapshot_from_run(
    run: SyncRun,
    *,
    include_word_diffs: bool = False,
) -> StatusSnapshot:
    wordlist_error = run.check_wordlist()
    if wordlist_error is not None:
        return StatusSnapshot(
            wordlist_count=0,
            diffs=(),
            skipped_unreadable=run.skipped_unreadable_dictionary_names(),
            skipped_corrupt=run.skipped_corrupt_dictionary_names(),
            wordlist_error=wordlist_error,
        )
    words = run.load_wordlist()
    return StatusSnapshot(
        wordlist_count=len(words),
        diffs=tuple(run.status_diffs(verbose=include_word_diffs)),
        skipped_unreadable=run.skipped_unreadable_dictionary_names(),
        skipped_corrupt=run.skipped_corrupt_dictionary_names(),
        destructive_risk=run.destructive_push_risk(),
        empty_wordlist=not words,
    )


def executable_push_preview(
    prepared=None,
    *,
    plan_identifier: str = "test-plan",
) -> PushPreview:
    if prepared is None:
        prepared = MagicMock()
        prepared.max_removals.return_value = 0
        prepared.targets = []
        prepared.skipped_unreadable = ()
        prepared.skipped_corrupt = ()
        prepared.skipped_blocked = ()
    return PushPreview(
        prepared=prepared,
        targets=(),
        additions=0,
        removals=0,
        warnings=(),
        created_at="2026-01-01T00:00:00+00:00",
        plan_identifier=plan_identifier,
        targets_to_update=0,
        unchanged=0,
        skipped=(),
        corrupt=(),
        blocked=(),
    )


def push_execution(
    result: PushResult | ExitCode,
    *,
    preview: PushPreview | None = None,
) -> PushExecution:
    preview = preview or executable_push_preview()
    outcome = (
        OperationOutcome.FAILED if isinstance(result, ExitCode) else OperationOutcome.COMPLETED
    )
    return PushExecution(
        prepared=preview.prepared,
        result=result,
        outcome=outcome,
        plan_identifier=preview.plan_identifier,
        push_preview=preview,
    )


def pull_preview_executable(
    wordlist_path: str,
    before: int,
    after: int,
    *,
    plan_identifier: str = "pull-plan",
) -> PullPreview:
    return PullPreview(
        wordlist_path=wordlist_path,
        additions=max(after - before, 0),
        before_count=before,
        after_count=after,
        sources_used=(),
        sources_skipped=(),
        source_rows=(),
        warnings=(),
        created_at="2026-01-01T00:00:00+00:00",
        plan_identifier=plan_identifier,
        merged_words=(),
    )


def pull_execution(
    before: int,
    after: int,
    *,
    preview: PullPreview | None = None,
    result: tuple[int, int] | ExitCode | None = None,
) -> PullExecution:
    if preview is None:
        preview = pull_preview_executable("/tmp/w.txt", before, after)
    execution_result = result if result is not None else (before, after)
    outcome = (
        OperationOutcome.FAILED
        if isinstance(execution_result, ExitCode)
        else OperationOutcome.COMPLETED
    )
    return PullExecution(
        preview=preview,
        result=execution_result,
        outcome=outcome,
        message=f"wordlist: {before} -> {after} (+{after - before})",
    )


def doctor_targets_from_run(run: SyncRun) -> DoctorTargetsSnapshot:
    targets: list[DoctorTargetView] = []
    for dictionary in run.dictionaries:
        status = dictionary_read_result(dictionary).status
        fmt = (
            dictionary.format.value
            if isinstance(dictionary.format, DictionaryFormat)
            else str(dictionary.format)
        )
        targets.append(
            DoctorTargetView(
                name=dictionary.name,
                path=dictionary.path,
                format=fmt,
                read_status=status.value,
            )
        )
    return DoctorTargetsSnapshot(
        wordlist_path=str(run.wordlist_file),
        targets=tuple(targets),
    )


def recoverable_preview(
    wordlist_path: str,
    *,
    preview_fingerprint: str = "tx-1",
) -> RecoveryPreview:
    return RecoveryPreview(
        status=RecoveryStatus.RECOVERABLE,
        transaction_id=preview_fingerprint,
        command="push",
        transaction_state="writing",
        started_at="2026-01-01T00:00:00+00:00",
        wordlist_path=wordlist_path,
        snapshot_directory=None,
        items=(),
        recoverable_count=1,
        conflict_count=0,
        failure_count=0,
        warnings=(),
        can_recover=True,
        can_discard=False,
        snapshots_valid=True,
        preview_fingerprint=preview_fingerprint,
    )


def recovery_execution(
    result: RecoverResult | ExitCode,
    *,
    preview: RecoveryPreview,
) -> RecoveryExecution:
    if isinstance(result, RecoverResult):
        outcome = (
            RecoveryOutcome.RECOVERED
            if not (result.failed or result.conflicts)
            else RecoveryOutcome.RECOVERY_INCOMPLETE
        )
    else:
        outcome = RecoveryOutcome.FAILED
    restored = result.restored if isinstance(result, RecoverResult) else ()
    skipped = result.skipped if isinstance(result, RecoverResult) else ()
    failed = result.failed if isinstance(result, RecoverResult) else ()
    conflicts = result.conflicts if isinstance(result, RecoverResult) else ()
    return RecoveryExecution(
        preview=preview,
        result=result,
        outcome=outcome,
        message="",
        restored=restored,
        skipped=skipped,
        failed=failed,
        conflicts=conflicts,
    )


def _service_mock(value: object) -> MagicMock:
    if isinstance(value, MagicMock):
        return value
    mock = MagicMock()
    mock.return_value = value
    return mock


@contextmanager
def patch_service(module, **methods: object) -> Iterator[None]:
    patched = {name: _service_mock(value) for name, value in methods.items()}
    with patch.multiple(f"{module.__name__}._SERVICE", **patched):
        yield


def patch_commands_service(**methods: object):
    return patch_service(__import__("spell_sync.commands", fromlist=["commands"]), **methods)


def patch_plan_service(**methods: object):
    return patch_service(__import__("spell_sync.plan_cmd", fromlist=["plan_cmd"]), **methods)


def patch_doctor_service(**methods: object):
    return patch_service(__import__("spell_sync.doctor", fromlist=["doctor"]), **methods)


def patch_recover_service(**methods: object):
    return patch_service(__import__("spell_sync.recover_cmd", fromlist=["recover_cmd"]), **methods)


@contextmanager
def patch_isolated_sync_run(run: SyncRun) -> Iterator[None]:
    from spell_sync.application.runtime_resolver import RuntimeResolver

    with (
        patch.object(RuntimeResolver, "sync_run", return_value=run),
        patch(
            "spell_sync.application._runtime_factory.discover_dictionaries",
            return_value=run.context.dictionaries,
        ),
    ):
        yield


@contextmanager
def patch_isolated_push(
    run: SyncRun,
    *,
    running_apps: bool = True,
    confirm_removals: bool = True,
) -> Iterator[None]:
    import spell_sync.commands as commands_mod

    with (
        patch_isolated_sync_run(run),
        patch(
            "spell_sync.application._runtime_factory.discover_dictionaries",
            return_value=run.context.dictionaries,
        ),
        patch.object(commands_mod, "_running_apps_check_for_push", return_value=running_apps),
        patch.object(
            commands_mod,
            "confirm_push_removals_for_preview",
            return_value=confirm_removals,
        ),
    ):
        yield


def push_plan_tuple(
    run: SyncRun,
    result: PushResult | ExitCode,
    *,
    verbose: bool = False,
    preview: PushPreview | None = None,
) -> tuple[PushPreview, tuple[DictionaryDiff, ...], PushResult | ExitCode]:
    preview = preview or executable_push_preview()
    diffs = tuple(run.status_diffs(verbose=verbose))
    return preview, diffs, result
