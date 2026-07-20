"""Single sync run: wordlist + local dictionary list."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Union

from .app_process_check import running_app_skip_reasons
from .dictionaries import Dictionary
from .exit_codes import ExitCode
from .io import read_hunspell_words, read_text_words
from .log import log
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
from .sync_context import RuntimeContext, as_dictionary_list, runtime_context_for
from .sync_models import DictionaryDiff, PushResult
from .validated_runtime import ValidatedRuntime
from .words import WordSet, clean_words, merge_case_duplicates, sort_words

# Re-export public result types for existing imports.
__all__ = ["PushResult", "DictionaryDiff", "SyncRun", "sync_run_for"]


class SyncRun:
    """Context for one operation: wordlist + dictionaries are assembled once."""

    def __init__(
        self,
        wordlist: Path | str | None = None,
        dictionaries: Optional[List[Dictionary]] = None,
        *,
        strict_push: bool = False,
        context: RuntimeContext | None = None,
    ) -> None:
        if context is not None:
            self._ctx = context
        else:
            self._ctx = RuntimeContext.build(
                wordlist=wordlist,
                dictionaries=dictionaries,
                strict_push=strict_push,
            )

    @property
    def wordlist_file(self) -> Path:
        return self._ctx.wordlist_file

    @property
    def dictionaries(self) -> List[Dictionary]:
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
    ) -> Union[tuple[int, int], ExitCode]:
        """Write a prepared pull merge without re-discovering dictionary sources."""
        unreadable = self.check_wordlist()
        if unreadable is not None:
            return unreadable
        if wordlist_fingerprint is not None:
            from .push_journal import file_content_hash

            current = file_content_hash(Path(self.wordlist_str))
            if current is not None and current != wordlist_fingerprint:
                log.abort("pull aborted — wordlist changed since preview.")
                return ExitCode.PUSH_ABORT
        if not self._write_wordlist(merged_words):
            log.abort("pull aborted — failed to write wordlist.")
            return ExitCode.PUSH_ABORT
        return before_count, after_count

    def pull_into_wordlist(self) -> Union[tuple[int, int], ExitCode]:
        """Merge enabled application custom dictionaries into the canonical wordlist.

        Pull reads only user custom dictionary files for enabled targets. Built-in
        application dictionaries are never read or inspected.

        Effective merge (case-insensitive):
        ``new_wordlist = canonical_wordlist ∪ readable_custom_dictionaries``
        """
        unreadable = self.check_wordlist()
        if unreadable is not None:
            return unreadable

        words = clean_words(read_text_words(self.wordlist_str))
        before = len(words)
        ordered = sort_words(words)
        seen_casefold = {word.casefold() for word in ordered}
        for dictionary, read_result in iter_wordlist_sources(
            self._ctx,
            unreadable_reason="no access — pull skipped",
            corrupt_reason="corrupt or unsupported — pull skipped",
        ):
            local_words = read_result.words
            for word in sort_words(local_words):
                key = word.casefold()
                if key not in seen_casefold:
                    ordered.append(word)
                    seen_casefold.add(key)
        merged = merge_case_duplicates(ordered)
        after = len(merged)
        from .push_journal import file_content_hash

        fingerprint = file_content_hash(Path(self.wordlist_str))
        return self.execute_prepared_pull(
            merged_words=tuple(merged),
            before_count=before,
            after_count=after,
            wordlist_fingerprint=fingerprint,
        )

    def pull_add_from(self, source: Path | str) -> Union[tuple[int, int], ExitCode]:
        """Merge words from an external UTF-8 or Hunspell file into wordlist."""
        unreadable = self.check_wordlist()
        if unreadable is not None:
            return unreadable

        source_path = Path(source)
        if not source_path.is_file():
            log.abort(f"pull source not found: {source_path}")
            return ExitCode.PUSH_ABORT

        if source_path.suffix.lower() == ".dic":
            external = read_hunspell_words(source_path, quiet=False)
        else:
            external = read_text_words(source_path, quiet=False)

        words = clean_words(read_text_words(self.wordlist_str))
        before = len(words)
        ordered = sort_words(words)
        seen_casefold = {word.casefold() for word in ordered}
        for word in sort_words(external):
            key = word.casefold()
            if key not in seen_casefold:
                ordered.append(word)
                seen_casefold.add(key)
        merged = merge_case_duplicates(ordered)
        after = len(merged)
        if not self._write_wordlist(merged):
            log.abort("pull aborted — failed to write wordlist.")
            return ExitCode.PUSH_ABORT
        return before, after

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

    def max_push_removals_from_prepared(self, prepared: PreparedPush) -> int:
        return prepared.max_removals()

    def plan_push(
        self,
        *,
        skip_names: frozenset[str] | None = None,
    ) -> PushResult | ExitCode:
        """Push plan without writing (dry-run)."""
        return self._run_push_transaction(dry_run=True, skip_names=skip_names)

    def push_from_wordlist(
        self,
        *,
        skip_names: frozenset[str] | None = None,
        prepared: PreparedPush | None = None,
    ) -> PushResult | ExitCode:
        """Derive each enabled custom dictionary from the canonical personal wordlist.

        Most targets receive the full canonical wordlist. Targets with an explicit
        subset function receive the applicable filtered subset.

        Built-in application dictionaries are not inspected, read, or modified.
        """
        return self._run_push_transaction(
            dry_run=False,
            skip_names=skip_names,
            prepared=prepared,
        )

    def check_wordlist(self) -> ExitCode | None:
        """None — OK; otherwise wordlist is unavailable."""
        return require_wordlist_readable(self._ctx)

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
    ) -> List[DictionaryDiff]:
        wordlist_words = self.load_wordlist()
        diffs: List[DictionaryDiff] = []
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
        words = self.load_wordlist()
        if not words or not destructive_push_would_block(self._ctx, words):
            return None
        max_local = max_local_dictionary_count(self._ctx, words)
        return (
            f"wordlist has {len(words)} words but local dictionaries have up to "
            f"{max_local} — run `pull` first, or push will abort"
        )

    def max_push_removals(self) -> int:
        """Largest per-dictionary word removal count that push would perform."""
        return max((diff.to_remove for diff in self.status_diffs()), default=0)

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
            dry_run=dry_run,
            running_app_skip_reasons_fn=running_app_skip_reasons,
        )
        if isinstance(result, PushAbort):
            return result.exit_code
        return result


def sync_run_for(
    wordlist: Path,
    *,
    strict_push: bool = False,
    validated: ValidatedRuntime | None = None,
) -> SyncRun:
    """Build SyncRun from an effective wordlist path."""
    return SyncRun(
        context=runtime_context_for(
            wordlist,
            strict_push=strict_push,
            validated=validated,
        )
    )
