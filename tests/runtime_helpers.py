"""Test helpers for explicit runtime construction."""

from __future__ import annotations

from pathlib import Path

from spell_sync.dictionaries import Dictionary
from spell_sync.push_journal import JournalLoadResult, JournalLoadStatus
from spell_sync.resolved_runtime import ResolvedRuntime
from spell_sync.runtime_identity import build_runtime_identity
from spell_sync.runtime_settings import RuntimeSettings
from spell_sync.settings import ConfigLoadResult, ConfigStatus
from spell_sync.sync_context import RuntimeContext
from spell_sync.sync_run import SyncRun


def make_runtime_context(
    wordlist: Path | str,
    *,
    dictionaries: tuple[Dictionary, ...] | list[Dictionary] = (),
    settings: RuntimeSettings | None = None,
    strict_push: bool = False,
) -> RuntimeContext:
    return RuntimeContext.build(
        wordlist,
        tuple(dictionaries),
        settings=settings or RuntimeSettings.defaults(),
        strict_push=strict_push,
    )


def make_resolved_runtime(
    wordlist: Path | str,
    *,
    context: RuntimeContext | None = None,
    config_status: ConfigStatus = ConfigStatus.ABSENT,
    journal_status: JournalLoadStatus = JournalLoadStatus.ABSENT,
) -> ResolvedRuntime:
    ctx = context or make_runtime_context(wordlist)
    config_result = ConfigLoadResult(config_status, {}, ())
    journal_result = JournalLoadResult(journal_status, None)
    identity = build_runtime_identity(ctx, config_result=config_result)
    return ResolvedRuntime(ctx, config_result, journal_result, identity)


def make_sync_run(
    wordlist: Path | str,
    *,
    dictionaries: tuple[Dictionary, ...] | list[Dictionary] = (),
    settings: RuntimeSettings | None = None,
    strict_push: bool = False,
) -> SyncRun:
    return SyncRun(
        context=make_runtime_context(
            wordlist,
            dictionaries=dictionaries,
            settings=settings,
            strict_push=strict_push,
        )
    )
