"""Interactive review of words push would remove."""

from __future__ import annotations

import sys

from .config import CONFIRM_YES
from .log import log
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


def list_removals(run) -> list[DictionaryDiff]:
    """Return diffs where push would remove words (for plan --removals)."""
    return _removal_diffs(run.status_diffs(verbose=True))


def print_removals(diffs: list[DictionaryDiff]) -> None:
    """Human-readable removal listing."""
    for diff in diffs:
        _print_removals(diff)
