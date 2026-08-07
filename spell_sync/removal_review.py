"""Interactive review of words push would remove."""

from __future__ import annotations

import sys

from .config import CONFIRM_YES
from .log import log
from .operation_reports import PushPreview
from .sync_run import DictionaryDiff


def _removal_diffs(diffs: list[DictionaryDiff]) -> list[DictionaryDiff]:
    return [diff for diff in diffs if diff.to_remove > 0]


def _print_removals(diff: DictionaryDiff) -> None:
    log.dictionary_status(
        diff.name,
        diff.target_count,
        diff.local_count,
        diff.to_add,
        diff.to_remove,
    )
    if diff.remove_words:
        log.dictionary_word_diff("remove (push)", diff.remove_words)


def _removal_targets(preview: PushPreview) -> list[tuple[str, int, frozenset[str]]]:
    return [
        (target.name, target.removals, target.removal_words)
        for target in preview.targets
        if target.removals > 0
    ]


def review_removals_interactive(
    run,
    *,
    interactive: bool | None = None,
) -> bool | None:
    """Show removal words; prompt in TTY. True proceed, False cancel, None interrupted."""
    diffs = _removal_diffs(run.status_diffs(verbose=True))
    if not diffs:
        return True

    total = sum(diff.to_remove for diff in diffs)
    log.warn(f"push would remove {total} word(s) across {len(diffs)} dictionary(s)")
    for diff in diffs:
        _print_removals(diff)

    is_interactive = sys.stdin.isatty() if interactive is None else interactive
    if not is_interactive:
        log.detail("non-interactive: listing only (use --yes to push without prompt)")
        return True

    try:
        answer = input("Continue push? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return None
    return answer in CONFIRM_YES


def review_removals_for_preview(
    preview: PushPreview,
    *,
    interactive: bool | None = None,
) -> bool | None:
    targets = _removal_targets(preview)
    if not targets:
        return True
    total = sum(removals for _, removals, _ in targets)
    log.warn(f"push would remove {total} word(s) across {len(targets)} dictionary(s)")
    for name, removals, words in targets:
        log.dictionary_status(name, 0, 0, 0, removals)
        if words:
            log.dictionary_word_diff("remove (push)", tuple(sorted(words, key=str.casefold)))
    is_interactive = sys.stdin.isatty() if interactive is None else interactive
    if not is_interactive:
        log.detail("non-interactive: listing only (use --yes to push without prompt)")
        return True
    try:
        answer = input("Continue push? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return None
    return answer in CONFIRM_YES


def list_removals(run) -> list[DictionaryDiff]:
    """Return diffs where push would remove words (for plan --removals)."""
    return _removal_diffs(run.status_diffs(verbose=True))


def list_removals_from_preview(preview: PushPreview) -> list[DictionaryDiff]:
    diffs: list[DictionaryDiff] = []
    for target in preview.targets:
        if target.removals <= 0:
            continue
        diffs.append(
            DictionaryDiff(
                name=target.name,
                target_count=0,
                local_count=0,
                to_add=target.additions,
                to_remove=target.removals,
                add_words=(),
                remove_words=tuple(sorted(target.removal_words, key=str.casefold)),
            )
        )
    return diffs


def print_removals(diffs: list[DictionaryDiff]) -> None:
    """Human-readable removal listing."""
    for diff in diffs:
        _print_removals(diff)
