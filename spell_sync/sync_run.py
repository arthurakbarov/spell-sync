"""Single sync run: wordlist + local dictionary list."""

from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

from .app_process_check import running_app_skip_reasons
from .dictionaries import Dictionary
from .exit_codes import ExitCode
from .guest_messages import (
    PULL_WORDLIST_APPEARED,
    PULL_WORDLIST_CHANGED,
    PULL_WORDLIST_WRITE_FAILED,
)
from .io import read_text_words
from .log import log
from .operation_reports import PullSourcePreview
from .push_abort import PushAbort
from .push_prepared import (
    PreparedPush,
    execute_prepared_push,
    plan_fingerprint_conflict,
    prepare_push,
)
from .push_setup import (
    destructive_push_would_block,
    iter_wordlist_sources,
    max_local_dictionary_count,
    require_wordlist_readable,
    skipped_dictionary_names,
)
from .read_outcome import ReadStatus
from .resolved_runtime import ResolvedRuntime
from .sync_context import RuntimeContext, as_dictionary_list
from .sync_models import DictionaryDiff, PushResult
from .words import WordSet, clean_words, merge_case_duplicates

# Public result types.
__all__ = [
    "DictionaryDiff",
    "PushResult",
    "SyncRun",
    "dictionary_diffs_from_prepared",
    "sync_run_for",
]


def dictionary_diffs_from_prepared(
    prepared: PreparedPush,
    *,
    verbose: bool = False,
) -> list[DictionaryDiff]:
    """Diffs from a frozen push plan — no second dictionary read."""
    sort_key = str.casefold
    diffs: list[DictionaryDiff] = []
    for item in prepared.targets:
        planned = item.planned
        diffs.append(
            DictionaryDiff(
                name=planned.dictionary.name,
                target_count=len(planned.target_words),
                local_count=len(planned.read_result.words),
                to_add=len(planned.additions),
                to_remove=len(planned.removals),
                add_words=tuple(sorted(planned.additions, key=sort_key)) if verbose else (),
                remove_words=tuple(sorted(planned.removals, key=sort_key)) if verbose else (),
            )
        )
    return diffs


class SyncRun:
    """Context for one operation: wordlist + dictionaries are assembled once."""

    def __init__(
        self,
        *,
        context: RuntimeContext,
    ) -> None:
        self._ctx = context

    @property
    def wordlist_file(self) -> Path:
        return self._ctx.wordlist_file

    @property
    def dictionaries(self) -> list[Dictionary]:
        return as_dictionary_list(self._ctx.dictionaries)

    @property
    def strict_push(self) -> bool:
        return self._ctx.strict_push

    @property
    def wordlist_str(self) -> str:
        return self._ctx.wordlist_str

    @property
    def context(self) -> RuntimeContext:
        return self._ctx

    def load_wordlist(self) -> WordSet:
        """Read the personal word list. Callers must ``check_wordlist`` first."""
        return clean_words(read_text_words(self.wordlist_str))

    def save_wordlist(self, words: WordSet) -> bool:
        return self._write_wordlist(words)

    def _write_wordlist(self, words: Iterable[str]) -> bool:
        merged = merge_case_duplicates(words)
        from .io import write_text_words

        return write_text_words(self.wordlist_str, merged, "utf-8", bom=False)

    def execute_prepared_pull(
        self,
        *,
        merged_words: tuple[str, ...],
        before_count: int,
        after_count: int,
        wordlist_fingerprint: str | None = None,
        source_rows: tuple[PullSourcePreview, ...] = (),
    ) -> tuple[int, int] | ExitCode:
        """Write a prepared pull merge without re-discovering dictionary sources."""
        unreadable = self.check_wordlist(allow_missing=True)
        if unreadable is not None:
            return unreadable
        from .push_journal import file_content_hash
        from .push_setup import verify_pull_source_fingerprints

        conflict_source = verify_pull_source_fingerprints(source_rows)
        if conflict_source is not None:
            log.abort(f"pull aborted — {conflict_source} changed since preview.")
            return ExitCode.PUSH_ABORT
        if wordlist_fingerprint is None:
            # Preview could not freeze content (missing/unhashable). Refuse if a
            # wordlist file is present now — otherwise we would overwrite blindly.
            if Path(self.wordlist_str).is_file():
                log.abort(PULL_WORDLIST_APPEARED)
                return ExitCode.PUSH_ABORT
        else:
            current = file_content_hash(Path(self.wordlist_str))
            if current != wordlist_fingerprint:
                log.abort(PULL_WORDLIST_CHANGED)
                return ExitCode.PUSH_ABORT
        if not self._write_wordlist(merged_words):
            log.abort(PULL_WORDLIST_WRITE_FAILED)
            return ExitCode.PUSH_ABORT
        return before_count, after_count

    def prepare_push_operation(
        self,
        *,
        skip_names: frozenset[str] | None = None,
    ) -> PreparedPush | ExitCode:
        unreadable = self.check_wordlist()
        if unreadable is not None:
            return unreadable
        words = self.load_wordlist()
        return prepare_push(self._ctx, words, skip_names=skip_names)

    def plan_push(
        self,
        *,
        skip_names: frozenset[str] | None = None,
        prepared: PreparedPush | None = None,
    ) -> PushResult | ExitCode:
        """Push plan without writing (dry-run)."""
        return self._run_push_transaction(
            dry_run=True,
            skip_names=skip_names,
            prepared=prepared,
        )

    def push_from_wordlist(
        self,
        *,
        skip_names: frozenset[str] | None = None,
        prepared: PreparedPush | None = None,
    ) -> PushResult | ExitCode:
        """Derive each enabled custom dictionary from the personal word list.

        Most targets receive the full personal word list. Targets with an explicit
        subset function receive the applicable filtered subset.

        Built-in application dictionaries are not inspected, read, or modified.
        """
        return self._run_push_transaction(
            dry_run=False,
            skip_names=skip_names,
            prepared=prepared,
        )

    def check_wordlist(self, *, allow_missing: bool = False) -> ExitCode | None:
        """None — OK; otherwise wordlist is unavailable."""
        return require_wordlist_readable(self._ctx, allow_missing=allow_missing)

    def skipped_unreadable_dictionary_names(self) -> tuple[str, ...]:
        return skipped_dictionary_names(self._ctx, ReadStatus.UNREADABLE)

    def skipped_corrupt_dictionary_names(self) -> tuple[str, ...]:
        return skipped_dictionary_names(
            self._ctx,
            ReadStatus.CORRUPT,
            ReadStatus.UNSUPPORTED,
        )

    def status_diffs(
        self,
        *,
        verbose: bool = False,
        quiet_unreadable: bool = False,
    ) -> list[DictionaryDiff]:
        if self.check_wordlist() is not None:
            return []
        wordlist_words = self.load_wordlist()
        diffs: list[DictionaryDiff] = []
        sort_key = str.casefold
        for dictionary, read_result in iter_wordlist_sources(
            self._ctx,
            unreadable_reason="no read access — diff skipped",
            corrupt_reason="corrupt or unsupported — diff skipped",
            quiet_unreadable=quiet_unreadable,
        ):
            local_words = read_result.words
            target = dictionary.target_words(wordlist_words)
            add_words = target - local_words
            remove_words = local_words - target
            diffs.append(
                DictionaryDiff(
                    name=dictionary.name,
                    target_count=len(target),
                    local_count=len(local_words),
                    to_add=len(add_words),
                    to_remove=len(remove_words),
                    add_words=tuple(sorted(add_words, key=sort_key)) if verbose else (),
                    remove_words=(tuple(sorted(remove_words, key=sort_key)) if verbose else ()),
                )
            )
        return diffs

    def destructive_push_risk(self) -> str | None:
        """Human-readable warning when push would wipe large local dictionaries."""
        if self.check_wordlist() is not None:
            return None
        words = self.load_wordlist()
        if not words or not destructive_push_would_block(self._ctx, words):
            return None
        max_local = max_local_dictionary_count(self._ctx, words)
        return (
            f"wordlist has {len(words)} words but local dictionaries have up to "
            f"{max_local} — run `pull` first, or push will abort"
        )

    def _run_push_transaction(
        self,
        *,
        dry_run: bool,
        skip_names: frozenset[str] | None = None,
        prepared: PreparedPush | None = None,
    ) -> PushResult | ExitCode:
        if prepared is None:
            prep = self.prepare_push_operation(skip_names=skip_names)
            if isinstance(prep, ExitCode):
                return prep
            prepared = prep
        else:
            conflict = plan_fingerprint_conflict(prepared)
            if conflict is not None:
                log.abort(
                    f"push aborted — {conflict} changed after confirmation (fingerprint conflict)."
                )
                return ExitCode.PUSH_ABORT

        result = execute_prepared_push(
            prepared,
            execution_context=self._ctx,
            dry_run=dry_run,
            running_app_skip_reasons_fn=lambda names: running_app_skip_reasons(
                names,
                settings=self._ctx.settings,
            ),
        )
        if isinstance(result, PushAbort):
            return result.exit_code
        return result


def sync_run_for(resolved: ResolvedRuntime, *, strict_push: bool | None = None) -> SyncRun:
    """Build SyncRun from an explicit resolved runtime."""
    ctx = resolved.context
    if strict_push is not None and strict_push != ctx.strict_push:
        ctx = replace(ctx, strict_push=strict_push)
    return SyncRun(context=ctx)
