"""Build UI-neutral push and pull preview snapshots."""

from datetime import UTC, datetime
from pathlib import Path

from ..dictionary_hints import project_honesty_warnings
from ..exit_codes import ExitCode
from ..push_journal import file_content_hash
from ..push_prepared import PreparedPush
from ..read_outcome import ReadStatus, dictionary_read_result
from ..runtime_identity import build_runtime_identity
from ..sync_run import SyncRun
from .reports import PullPreview, PullSourcePreview, PushPreview, TargetPreview


def _plan_identifier(prepared: PreparedPush) -> str:
    wordlist_path = Path(prepared.ctx.wordlist_str)
    try:
        if prepared.wordlist_rendered is not None:
            return prepared.wordlist_rendered.sha256[:8]
        digest = file_content_hash(wordlist_path)
        if digest:
            return digest[:8]
    except OSError:
        pass
    return f"{len(prepared.targets)}targets"


def _target_preview_status(additions: int, removals: int) -> str:
    if additions == 0 and removals == 0:
        return "Unchanged"
    if removals > 0:
        return "Review"
    return "Ready"


def build_push_preview(
    prepared: PreparedPush | None,
    *,
    prepare_error: ExitCode | None = None,
    wordlist_error: ExitCode | None = None,
) -> PushPreview:
    created_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    if wordlist_error is not None:
        return PushPreview.unavailable(
            created_at=created_at,
            wordlist_error=wordlist_error,
        )
    if prepare_error is not None or prepared is None:
        return PushPreview.unavailable(
            created_at=created_at,
            plan_identifier="blocked",
            prepare_error=prepare_error,
        )

    targets: list[TargetPreview] = []
    total_add = 0
    total_remove = 0
    to_update = 0
    unchanged = 0
    for item in prepared.targets:
        additions = len(item.planned.additions)
        removals = len(item.planned.removals)
        total_add += additions
        total_remove += removals
        status = _target_preview_status(additions, removals)
        if status == "Unchanged":
            unchanged += 1
        else:
            to_update += 1
        targets.append(
            TargetPreview(
                name=item.planned.dictionary.name,
                additions=additions,
                removals=removals,
                status=status,
                removal_words=item.planned.removals,
                addition_words=item.planned.additions,
            )
        )

    warnings: list[str] = []
    if prepared.skipped_unreadable:
        warnings.append(f"Skipped unreadable: {', '.join(prepared.skipped_unreadable)}")
    if prepared.skipped_corrupt:
        warnings.append(f"Skipped corrupt: {', '.join(prepared.skipped_corrupt)}")
    if prepared.skipped_blocked:
        warnings.append(f"Skipped blocked: {', '.join(prepared.skipped_blocked)}")
    warnings.extend(
        project_honesty_warnings(
            Path(prepared.ctx.wordlist_str),
            settings=prepared.ctx.settings,
        )
    )

    return PushPreview(
        prepared=prepared,
        targets=tuple(targets),
        additions=total_add,
        removals=total_remove,
        warnings=tuple(warnings),
        created_at=created_at,
        plan_identifier=_plan_identifier(prepared),
        targets_to_update=to_update,
        unchanged=unchanged,
        skipped=prepared.skipped_unreadable,
        corrupt=prepared.skipped_corrupt,
        blocked=prepared.skipped_blocked,
    )


def build_pull_preview(run: SyncRun) -> PullPreview:
    """Compute the Collect merge preview without writing the personal word list.

    Merges words from readable enabled application custom dictionaries into the
    current personal word list using case-insensitive deduplication.
    """
    from ..io import read_text_words
    from ..read_outcome import is_readable_for_union
    from ..words import added_words_casefold, clean_words, merge_case_duplicates

    created_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    wordlist_path = run.wordlist_str
    wordlist_error = run.check_wordlist(allow_missing=True)
    if wordlist_error is not None:
        return PullPreview.unavailable(
            wordlist_path=wordlist_path,
            created_at=created_at,
            wordlist_error=wordlist_error,
        )

    words = clean_words(read_text_words(wordlist_path))
    ordered = merge_case_duplicates(words)
    before = len(ordered)
    addition_words: set[str] = set()
    sources_used: list[str] = []
    sources_skipped: list[str] = []
    source_rows: list[PullSourcePreview] = []
    warnings: list[str] = []

    for dictionary in run.context.dictionaries:
        read_result = dictionary_read_result(dictionary)
        status = read_result.status
        if status is ReadStatus.UNREADABLE:
            sources_skipped.append(dictionary.name)
            source_rows.append(
                PullSourcePreview(
                    dictionary.name,
                    "skipped",
                    detail="no access — pull skipped",
                )
            )
            warnings.append(f"Skipped unreadable: {dictionary.name}")
            continue
        if status in (ReadStatus.CORRUPT, ReadStatus.UNSUPPORTED):
            sources_skipped.append(dictionary.name)
            source_rows.append(
                PullSourcePreview(
                    dictionary.name,
                    "skipped",
                    detail="corrupt or unsupported — pull skipped",
                )
            )
            warnings.append(f"Skipped corrupt: {dictionary.name}")
            continue
        if not is_readable_for_union(status):
            sources_skipped.append(dictionary.name)
            source_rows.append(PullSourcePreview(dictionary.name, "skipped", detail=status.value))
            continue
        added = added_words_casefold(ordered, read_result.words)
        ordered.extend(added)
        addition_words.update(added)
        contributed = len(added)
        sources_used.append(dictionary.name)
        fingerprint = read_result.fingerprint
        source_rows.append(
            PullSourcePreview(
                dictionary.name,
                "used",
                words_contributed=contributed,
                path=dictionary.path,
                content_sha256=fingerprint.sha256 if fingerprint is not None else None,
            )
        )

    merged = merge_case_duplicates(ordered)
    after = len(merged)
    digest = file_content_hash(Path(wordlist_path))
    plan_id = (digest or f"{before}-{after}")[:8]
    runtime_identity = build_runtime_identity(run.context)
    warnings.extend(project_honesty_warnings(Path(wordlist_path), settings=run.context.settings))
    return PullPreview(
        wordlist_path=wordlist_path,
        additions=len(addition_words),
        before_count=before,
        after_count=after,
        sources_used=tuple(sources_used),
        sources_skipped=tuple(sources_skipped),
        source_rows=tuple(source_rows),
        warnings=tuple(warnings),
        created_at=created_at,
        plan_identifier=plan_id,
        merged_words=tuple(merged),
        addition_words=frozenset(addition_words),
        wordlist_fingerprint=digest,
        runtime_identity=runtime_identity,
    )


def build_pull_add_from_preview(run: SyncRun, source: Path) -> PullPreview:
    """Preview merging words from an external file into the personal word list."""
    from ..io import read_hunspell_words, read_text_words, wordlist_unreadable
    from ..words import added_words_casefold, clean_words, merge_case_duplicates

    created_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    wordlist_path = run.wordlist_str
    wordlist_error = run.check_wordlist(allow_missing=True)
    if wordlist_error is not None:
        return PullPreview.unavailable(
            wordlist_path=wordlist_path,
            created_at=created_at,
            wordlist_error=wordlist_error,
        )

    source_path = Path(source)
    if not source_path.is_file():
        return PullPreview.unavailable(
            wordlist_path=wordlist_path,
            created_at=created_at,
            prepare_error=ExitCode.PUSH_ABORT,
        )

    # Fail closed: undecodable or control-laden sources must not look like a merge.
    if wordlist_unreadable(source_path):
        return PullPreview.unavailable(
            wordlist_path=wordlist_path,
            created_at=created_at,
            sources_skipped=(str(source_path),),
            source_rows=(PullSourcePreview(str(source_path), "skipped", detail="unreadable"),),
            warnings=(f"Skipped unreadable: {source_path}",),
            prepare_error=ExitCode.WORDLIST_UNREADABLE,
        )
    if source_path.suffix.lower() == ".dic":
        external = read_hunspell_words(source_path, quiet=False)
    else:
        external = read_text_words(source_path, quiet=False)

    words = clean_words(read_text_words(wordlist_path))
    ordered = merge_case_duplicates(words)
    before = len(ordered)
    added = added_words_casefold(ordered, external)
    ordered.extend(added)
    addition_words = set(added)
    merged = merge_case_duplicates(ordered)
    after = len(merged)
    digest = file_content_hash(Path(wordlist_path))
    plan_id = (digest or f"{before}-{after}")[:8]
    source_label = str(source_path)
    source_digest = file_content_hash(source_path)
    runtime_identity = build_runtime_identity(run.context)
    return PullPreview(
        wordlist_path=wordlist_path,
        additions=len(addition_words),
        before_count=before,
        after_count=after,
        sources_used=(source_label,),
        sources_skipped=(),
        source_rows=(
            PullSourcePreview(
                source_label,
                "used",
                words_contributed=len(addition_words),
                path=str(source_path),
                content_sha256=source_digest,
            ),
        ),
        warnings=tuple(
            project_honesty_warnings(Path(wordlist_path), settings=run.context.settings)
        ),
        created_at=created_at,
        plan_identifier=plan_id,
        merged_words=tuple(merged),
        addition_words=frozenset(addition_words),
        wordlist_fingerprint=digest,
        runtime_identity=runtime_identity,
    )
