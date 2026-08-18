"""Test helpers for explicit runtime construction."""

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
    identity = build_runtime_identity(ctx)
    return ResolvedRuntime(ctx, config_result, journal_result, identity)


def make_sync_run(
    wordlist: Path | str,
    *,
    dictionaries: tuple[Dictionary, ...] | list[Dictionary] = (),
    settings: RuntimeSettings | None = None,
    strict_push: bool = False,
) -> SyncRun:
    path = Path(wordlist)
    if settings is None:
        from spell_sync.settings import load_config_result, project_config_path

        if project_config_path(path).is_file():
            settings = load_config_result(wordlist=path).runtime_settings()
    return SyncRun(
        context=make_runtime_context(
            wordlist,
            dictionaries=dictionaries,
            settings=settings,
            strict_push=strict_push,
        )
    )


def pull_into_wordlist(run: SyncRun):
    """Test helper: live pull via build_pull_preview + execute_prepared_pull."""
    from spell_sync.application.push_pull_preview_builders import build_pull_preview

    preview = build_pull_preview(run)
    if preview.wordlist_error is not None:
        return preview.wordlist_error
    return run.execute_prepared_pull(
        merged_words=preview.merged_words,
        before_count=preview.before_count,
        after_count=preview.after_count,
        wordlist_fingerprint=preview.wordlist_fingerprint,
        source_rows=preview.source_rows,
    )


def pull_add_from(run: SyncRun, source: Path | str):
    """Test helper: live add-from via build_pull_add_from_preview + execute_prepared_pull."""
    from spell_sync.application.push_pull_preview_builders import build_pull_add_from_preview

    preview = build_pull_add_from_preview(run, Path(source))
    if preview.wordlist_error is not None:
        return preview.wordlist_error
    if preview.prepare_error is not None:
        return preview.prepare_error
    return run.execute_prepared_pull(
        merged_words=preview.merged_words,
        before_count=preview.before_count,
        after_count=preview.after_count,
        wordlist_fingerprint=preview.wordlist_fingerprint,
        source_rows=preview.source_rows,
    )
