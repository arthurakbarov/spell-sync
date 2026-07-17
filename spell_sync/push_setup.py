"""Push planning: guards, dictionary filtering, and result assembly."""

from __future__ import annotations

from typing import Iterator, List, NamedTuple, Union

from .config import TCC_ACCESS_HINT, push_guard_local_min, push_guard_wordlist_max
from .dictionaries import Dictionary
from .exit_codes import ExitCode
from .io import read_text_words, wordlist_unreadable
from .log import log
from .push_plan import PushPlan, build_push_plan, max_local_word_count
from .push_transaction import PushTransaction, dictionaries_ready_to_write
from .read_outcome import (
    DictionaryReadResult,
    ReadStatus,
    dictionary_read_result,
    is_readable_for_union,
)
from .skip_reasons import PUSH_SKIP_DETAILS, PushSkipReason
from .sync_context import RuntimeContext
from .sync_models import PushResult
from .words import WordSet, sort_words


class PushSetup(NamedTuple):
    plan: PushPlan
    dictionaries: List[Dictionary]
    skipped_unreadable: List[str]
    skipped_corrupt: List[str]
    skipped_blocked: List[str]


def warn_dictionary_skipped(name: str, reason: str) -> None:
    """Unified warning format for an unavailable dictionary."""
    log.warn(f"  {name}: {reason} {TCC_ACCESS_HINT}")


def require_wordlist_readable(ctx: RuntimeContext) -> ExitCode | None:
    if wordlist_unreadable(ctx.wordlist_str):
        log.abort(f"wordlist unreadable {TCC_ACCESS_HINT}")
        return ExitCode.WORDLIST_UNREADABLE
    return None


def wordlist_needs_rewrite(ctx: RuntimeContext, words: WordSet) -> bool:
    path = ctx.wordlist_file
    if not path.exists():
        return True
    on_disk = sort_words(read_text_words(ctx.wordlist_str, quiet=True))
    return on_disk != sort_words(words)


def setup_push(
    ctx: RuntimeContext,
    words: WordSet,
    *,
    skip_names: frozenset[str] | None = None,
) -> PushSetup | ExitCode:
    plan_or_exit = build_push_plan(ctx, words, skip_names=skip_names)
    if isinstance(plan_or_exit, ExitCode):
        return plan_or_exit
    plan = plan_or_exit

    blocked = destructive_push_blocked(ctx, words, plan=plan)
    if blocked is not None:
        return blocked

    skipped_unreadable = list(plan.skipped_unreadable)
    skipped_corrupt = list(plan.skipped_corrupt)
    skipped_blocked = list(plan.skipped_blocked)

    for name in skipped_unreadable:
        warn_dictionary_skipped(name, "no access — push skipped")
    for name in skipped_corrupt:
        warn_dictionary_skipped(name, "corrupt or unsupported — push skipped")

    blocked_exit = strict_push_blocked(
        ctx,
        skipped_unreadable + skipped_corrupt,
        "unavailable",
    )
    if blocked_exit is not None:
        return blocked_exit

    if not ctx.dictionaries:
        return PushSetup(
            plan,
            [],
            skipped_unreadable,
            skipped_corrupt,
            skipped_blocked,
        )

    dictionaries = [target.dictionary for target in plan.targets]
    if not dictionaries:
        if skipped_unreadable or skipped_corrupt or skipped_blocked:
            return PushSetup(
                plan,
                [],
                skipped_unreadable,
                skipped_corrupt,
                skipped_blocked,
            )
        log.abort("push aborted — no dictionary available for writing.")  # pragma: no cover
        return ExitCode.PUSH_ABORT  # pragma: no cover

    return PushSetup(
        plan,
        dictionaries,
        skipped_unreadable,
        skipped_corrupt,
        skipped_blocked,
    )


def make_push_result(
    ctx: RuntimeContext,
    words: WordSet,
    skipped_unreadable: List[str],
    skipped_corrupt: List[str],
    skipped_blocked: List[str],
    skipped_backup: set[str],
    skipped_running: set[str],
    written: tuple[str, ...],
    *,
    running_details: dict[str, str] | None = None,
) -> PushResult:
    skipped_names = (
        set(skipped_unreadable)
        | set(skipped_corrupt)
        | set(skipped_blocked)
        | skipped_backup
        | skipped_running
    )
    skipped = tuple(d.name for d in ctx.dictionaries if d.name in skipped_names)
    skipped_reasons: dict[str, str] = {}
    skipped_details: dict[str, str] = {}
    for name in skipped_unreadable:
        skipped_reasons[name] = PushSkipReason.UNREADABLE
    for name in skipped_corrupt:
        skipped_reasons[name] = PushSkipReason.CORRUPT
    for name in skipped_blocked:
        skipped_reasons.setdefault(name, PushSkipReason.BLOCKED_BY_USER)
    for name in skipped_backup:
        skipped_reasons.setdefault(name, PushSkipReason.BACKUP_FAILED)
    for name in skipped_running:
        skipped_reasons.setdefault(name, PushSkipReason.RUNNING_APP)
    for name in skipped:
        reason = skipped_reasons.get(name)
        if reason and name not in skipped_details:
            skipped_details[name] = PUSH_SKIP_DETAILS.get(reason, reason)
    if running_details:
        skipped_details.update(running_details)
    return PushResult(len(words), written, skipped, skipped_reasons, skipped_details)


def prepare_writable_dictionaries(
    ctx: RuntimeContext,
    tx: PushTransaction,
    dictionaries: List[Dictionary],
) -> Union[tuple[List[Dictionary], set[str]], ExitCode]:
    if tx.wordlist_backup.existed_before and tx.wordlist_backup.backup is None:
        log.abort("push aborted — wordlist backup failed.")
        return ExitCode.PUSH_ABORT

    writable = dictionaries_ready_to_write(dictionaries, tx.dictionary_backups)
    if dictionaries and not writable:
        log.abort("push aborted — backup failed for every dictionary.")
        return ExitCode.PUSH_ABORT

    skipped_backup = {d.name for d in dictionaries if d not in writable}
    for name in sorted(skipped_backup, key=str.casefold):
        warn_dictionary_skipped(name, "backup failed — push skipped")
    blocked = strict_push_blocked(ctx, sorted(skipped_backup), "backup failed")
    if blocked is not None:
        return blocked
    return writable, skipped_backup


def strict_push_blocked(ctx: RuntimeContext, skipped: list[str], reason: str) -> ExitCode | None:
    if not ctx.strict_push or not skipped:
        return None
    log.abort(f"push aborted (--strict) — {reason} for: {', '.join(skipped)}")
    return ExitCode.PUSH_ABORT


def destructive_push_blocked(
    ctx: RuntimeContext,
    words: WordSet,
    *,
    plan: PushPlan | None = None,
) -> ExitCode | None:
    if not destructive_push_would_block(ctx, words, plan=plan):
        return None
    max_local = (
        max_local_word_count(plan) if plan is not None else max_local_dictionary_count(ctx, words)
    )
    log.abort(
        f"push aborted — wordlist has {len(words)} words but local dictionaries "
        f"have up to {max_local}. Run `pull` first to merge existing words."
    )
    return ExitCode.PUSH_ABORT


def destructive_push_would_block(
    ctx: RuntimeContext,
    words: WordSet,
    *,
    plan: PushPlan | None = None,
) -> bool:
    wordlist_count = len(words)
    if wordlist_count > push_guard_wordlist_max():
        return False
    max_local = (
        max_local_word_count(plan) if plan is not None else max_local_dictionary_count(ctx, words)
    )
    return max_local > push_guard_local_min() and wordlist_count < max_local


def max_local_dictionary_count(ctx: RuntimeContext, words: WordSet | None = None) -> int:
    if words is None:
        words = clean_words_from_ctx(ctx)
    plan = build_push_plan(ctx, words)
    if isinstance(plan, ExitCode):
        return 0
    return max_local_word_count(plan)


def clean_words_from_ctx(ctx: RuntimeContext) -> WordSet:
    from .words import clean_words

    return clean_words(read_text_words(ctx.wordlist_str))


def iter_wordlist_sources(
    ctx: RuntimeContext,
    *,
    unreadable_reason: str,
    corrupt_reason: str,
    quiet_unreadable: bool = False,
) -> Iterator[tuple[Dictionary, DictionaryReadResult]]:
    """Dictionaries that contribute to pull or status diffs."""
    for dictionary in ctx.dictionaries:
        read_result = dictionary_read_result(dictionary)
        status = read_result.status
        if status is ReadStatus.UNREADABLE:
            if not quiet_unreadable:
                warn_dictionary_skipped(dictionary.name, unreadable_reason)
            continue
        if status in (ReadStatus.CORRUPT, ReadStatus.UNSUPPORTED):
            if not quiet_unreadable:
                warn_dictionary_skipped(dictionary.name, corrupt_reason)
            continue
        if not is_readable_for_union(status):
            continue  # pragma: no cover -- defensive; all enum values handled above
        yield dictionary, read_result


def skipped_dictionary_names(
    ctx: RuntimeContext,
    *statuses: ReadStatus,
) -> tuple[str, ...]:
    skipped: List[str] = []
    for dictionary in ctx.dictionaries:
        status = dictionary_read_result(dictionary).status
        if status in statuses:
            skipped.append(dictionary.name)
    return tuple(skipped)
