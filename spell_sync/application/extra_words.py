"""Inventory extra words (app-only) and surgically subtract rejects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..dictionary_hints import project_honesty_warnings
from ..exit_codes import ExitCode
from ..push_journal import file_content_hash
from ..read_outcome import ReadStatus, dictionary_read_result, is_readable_for_union
from ..runtime_identity import RuntimeIdentity, build_runtime_identity
from ..sync_run import SyncRun
from ..words import WordSet, clean_words, sort_words


@dataclass(frozen=True, slots=True)
class ExtraWordRow:
    word: str
    sources: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExtraWordSource:
    name: str
    path: str
    content_sha256: str | None


@dataclass(frozen=True, slots=True)
class ExtraWordInventory:
    wordlist_path: str
    rows: tuple[ExtraWordRow, ...]
    sources: tuple[ExtraWordSource, ...]
    warnings: tuple[str, ...]
    created_at: str
    wordlist_fingerprint: str | None
    runtime_identity: RuntimeIdentity | None
    wordlist_error: ExitCode | None = None

    @property
    def is_available(self) -> bool:
        return self.wordlist_error is None

    @classmethod
    def unavailable(
        cls,
        *,
        wordlist_path: str,
        created_at: str,
        wordlist_error: ExitCode,
    ) -> ExtraWordInventory:
        return cls(
            wordlist_path=wordlist_path,
            rows=(),
            sources=(),
            warnings=(),
            created_at=created_at,
            wordlist_fingerprint=None,
            runtime_identity=None,
            wordlist_error=wordlist_error,
        )

    @classmethod
    def empty(
        cls,
        *,
        wordlist_path: str,
        created_at: str | None = None,
        wordlist_fingerprint: str | None = None,
        runtime_identity: RuntimeIdentity | None = None,
        warnings: tuple[str, ...] = (),
    ) -> ExtraWordInventory:
        stamp = created_at or datetime.now(UTC).replace(microsecond=0).isoformat()
        return cls(
            wordlist_path=wordlist_path,
            rows=(),
            sources=(),
            warnings=warnings,
            created_at=stamp,
            wordlist_fingerprint=wordlist_fingerprint,
            runtime_identity=runtime_identity,
        )


@dataclass(frozen=True, slots=True)
class ExtraWordsWipeResult:
    ok: bool
    written: tuple[str, ...]
    skipped: tuple[str, ...]
    conflict: bool = False
    write_failed: bool = False


def build_extra_word_inventory(run: SyncRun) -> ExtraWordInventory:
    """List words that appear in enabled dictionaries but not in the word list.

    One row per casefold key. ``sources`` lists every readable dictionary that
    contains that word (unlike Collect preview, which attributes a word once).
    """
    from ..io import read_text_words

    created_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    wordlist_path = run.wordlist_str
    wordlist_error = run.check_wordlist(allow_missing=True)
    if wordlist_error is not None:
        return ExtraWordInventory.unavailable(
            wordlist_path=wordlist_path,
            created_at=created_at,
            wordlist_error=wordlist_error,
        )

    wordlist_keys = {word.casefold() for word in clean_words(read_text_words(wordlist_path))}
    extras: dict[str, tuple[str, list[str]]] = {}
    sources: list[ExtraWordSource] = []
    warnings: list[str] = []

    for dictionary in run.context.dictionaries:
        read_result = dictionary_read_result(dictionary)
        status = read_result.status
        if status is ReadStatus.UNREADABLE:
            warnings.append(f"Skipped unreadable: {dictionary.name}")
            continue
        if status in (ReadStatus.CORRUPT, ReadStatus.UNSUPPORTED):
            warnings.append(f"Skipped corrupt: {dictionary.name}")
            continue
        if not is_readable_for_union(status):
            continue
        fingerprint = read_result.fingerprint
        sources.append(
            ExtraWordSource(
                name=dictionary.name,
                path=dictionary.path,
                content_sha256=fingerprint.sha256 if fingerprint is not None else None,
            )
        )
        for word in sort_words(read_result.words):
            key = word.casefold()
            if key in wordlist_keys:
                continue
            existing = extras.get(key)
            if existing is None:
                extras[key] = (word, [dictionary.name])
                continue
            if dictionary.name not in existing[1]:
                existing[1].append(dictionary.name)

    warnings.extend(project_honesty_warnings(Path(wordlist_path), settings=run.context.settings))
    rows = tuple(
        ExtraWordRow(display, tuple(names))
        for _key, (display, names) in sorted(extras.items(), key=lambda item: item[0])
    )
    return ExtraWordInventory(
        wordlist_path=wordlist_path,
        rows=rows,
        sources=tuple(sources),
        warnings=tuple(warnings),
        created_at=created_at,
        wordlist_fingerprint=file_content_hash(Path(wordlist_path)),
        runtime_identity=build_runtime_identity(run.context),
    )


def subtract_extra_words_from_sources(
    run: SyncRun,
    inventory: ExtraWordInventory,
    words: tuple[str, ...],
) -> ExtraWordsWipeResult:
    """Remove selected extra words from every recorded source that contains them.

    Does not rewrite dictionaries to the word list (not Update). Other extra
    words on disk stay. Empty ``words`` is a no-op success.
    """
    reject_keys = {word.casefold() for word in words}
    if not reject_keys:
        return ExtraWordsWipeResult(ok=True, written=(), skipped=())

    if inventory.runtime_identity is not None:
        current_identity = build_runtime_identity(run.context)
        if inventory.runtime_identity != current_identity:
            return ExtraWordsWipeResult(ok=False, written=(), skipped=(), conflict=True)

    needed: set[str] = set()
    for row in inventory.rows:
        if row.word.casefold() in reject_keys:
            needed.update(row.sources)

    source_by_name = {source.name: source for source in inventory.sources}
    written: list[str] = []
    skipped: list[str] = []

    for dictionary in run.context.dictionaries:
        if dictionary.name not in needed:
            continue
        recorded = source_by_name.get(dictionary.name)
        if recorded is None:
            return ExtraWordsWipeResult(ok=False, written=tuple(written), skipped=(), conflict=True)
        current_hash = file_content_hash(Path(dictionary.path))
        if recorded.content_sha256 != current_hash:
            return ExtraWordsWipeResult(ok=False, written=tuple(written), skipped=(), conflict=True)
        read_result = dictionary_read_result(dictionary)
        if read_result.status in (
            ReadStatus.UNREADABLE,
            ReadStatus.CORRUPT,
            ReadStatus.UNSUPPORTED,
        ):
            return ExtraWordsWipeResult(ok=False, written=tuple(written), skipped=(), conflict=True)
        if not is_readable_for_union(read_result.status):
            skipped.append(dictionary.name)
            continue
        remaining: WordSet = {
            word for word in read_result.words if word.casefold() not in reject_keys
        }
        if remaining == set(read_result.words):
            skipped.append(dictionary.name)
            continue
        if not dictionary.write_contents(remaining, quiet=True):
            return ExtraWordsWipeResult(
                ok=False,
                written=tuple(written),
                skipped=tuple(skipped),
                write_failed=True,
            )
        written.append(dictionary.name)

    return ExtraWordsWipeResult(ok=True, written=tuple(written), skipped=tuple(skipped))
