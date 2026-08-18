"""Guest-facing push preview copy for removal/addition counts.

Summary lines use unique words across apps (one word on three apps counts as 1).
Per-target table cells stay as per-app counts. Detail screens list unique words;
addition review further omits full-sync dumps using ``PUSH_SMALL_DELTA_REVIEW_MAX``
(same heuristic as ``max_removals_without_confirm``).
"""

from collections import defaultdict

from ..config import PUSH_SMALL_DELTA_REVIEW_MAX
from .field_blocks import format_aligned_fields
from .product_concepts import (
    DICTIONARIES_TO_UPDATE_LABEL,
    PUSH_DIRECTION_LABEL,
    PUSH_PREVIEW_CONTEXT,
    PUSH_PREVIEW_SAFETY,
    PUSH_REMOVALS_WARNING,
    UPDATE_APPS_LABEL,
    numbered_word_prefix,
)
from .reports import PushPreview, TargetPreview


def unique_removal_words(preview: PushPreview) -> frozenset[str]:
    words: set[str] = set()
    for target in preview.targets:
        words.update(target.removal_words)
    return frozenset(words)


def unique_addition_words(preview: PushPreview) -> frozenset[str]:
    words: set[str] = set()
    for target in preview.targets:
        words.update(target.addition_words)
    return frozenset(words)


def push_detail_buttons_visible(preview: PushPreview) -> tuple[bool, bool]:
    """Whether View additions / View removals have non-empty detail lists.

    Additions use the small-delta reviewable set (same as the detail screen).
    """
    return (
        bool(unique_reviewable_addition_words(preview)),
        bool(unique_removal_words(preview)),
    )


def removal_apps_by_word(preview: PushPreview) -> dict[str, tuple[str, ...]]:
    apps: dict[str, list[str]] = defaultdict(list)
    for target in preview.targets:
        if not target.removal_words:
            continue
        for word in sorted(target.removal_words):
            apps[word].append(target.name)
    return {word: tuple(names) for word, names in apps.items()}


def format_push_preview_summary(
    preview: PushPreview,
    *,
    title: str | None = None,
    include_safety: bool = True,
) -> str:
    """At-a-glance push preview: safety, counts, and short filtering/redundancy context."""
    headline = title if title is not None else f"{UPDATE_APPS_LABEL} preview (no writes yet)"
    lines = [headline, ""]
    if include_safety:
        lines.extend([PUSH_PREVIEW_SAFETY, ""])
    lines.extend([PUSH_DIRECTION_LABEL, ""])
    lines.extend(
        format_aligned_fields(
            [
                (DICTIONARIES_TO_UPDATE_LABEL, preview.targets_to_update),
                ("Words to add", len(unique_addition_words(preview))),
                ("Words to remove", len(unique_removal_words(preview))),
                ("Unchanged", preview.unchanged),
            ]
        )
    )
    lines.extend(["", PUSH_PREVIEW_CONTEXT])
    if preview.removals > 0:
        lines.extend(["", f"! {PUSH_REMOVALS_WARNING}"])
    if preview.skipped:
        lines.append(f"Skipped: {', '.join(preview.skipped)}")
    if preview.corrupt:
        lines.append(f"Corrupt: {', '.join(preview.corrupt)}")
    if preview.warnings:
        lines.append(f"! Warnings: {', '.join(preview.warnings)}")
    return "\n".join(lines)


def format_additions_confirm_counts(preview: PushPreview) -> str:
    return f"{len(unique_addition_words(preview))} additions"


def format_removals_confirm_counts(preview: PushPreview) -> str:
    """Short count phrase for the typed-confirm modal footer lines."""
    unique = len(unique_removal_words(preview))
    if unique <= 0:
        return "0 removals"
    return f"{unique} removals"


def format_removals_confirm_sentence(preview: PushPreview) -> str:
    """Full sentence clause after 'This update will remove ...'."""
    unique = len(unique_removal_words(preview))
    if unique <= 0:
        return "0 words"
    return f"{unique} words"


def format_removals_detail_summary(*, target_label: str, preview: PushPreview) -> str:
    unique = len(unique_removal_words(preview))
    if unique <= 0:
        return f"Removals across {target_label}: 0 words"
    return f"Removals across {target_label}: {unique} word(s)"


def format_removals_detail_body(preview: PushPreview) -> str:
    by_word = removal_apps_by_word(preview)
    if not by_word:
        return "No words planned for removal."
    lines: list[str] = []
    ordered = sorted(by_word)
    total = len(ordered)
    for index, word in enumerate(ordered, start=1):
        apps = ", ".join(by_word[word])
        lines.append(f"{numbered_word_prefix(index, total)} {word}")
        lines.append(f"  {apps}")
    return "\n".join(lines)


def small_delta_addition_targets(
    preview: PushPreview,
    *,
    max_additions: int = PUSH_SMALL_DELTA_REVIEW_MAX,
) -> tuple[TargetPreview, ...]:
    """Targets whose addition count is reviewable (not a full-sync dump)."""
    return tuple(
        target
        for target in preview.targets
        if 0 < target.additions <= max_additions and target.addition_words
    )


def omitted_full_sync_addition_targets(
    preview: PushPreview,
    *,
    max_additions: int = PUSH_SMALL_DELTA_REVIEW_MAX,
) -> tuple[TargetPreview, ...]:
    return tuple(target for target in preview.targets if target.additions > max_additions)


def unique_reviewable_addition_words(
    preview: PushPreview,
    *,
    max_additions: int = PUSH_SMALL_DELTA_REVIEW_MAX,
) -> frozenset[str]:
    words: set[str] = set()
    for target in small_delta_addition_targets(preview, max_additions=max_additions):
        words.update(target.addition_words)
    return frozenset(words)


def addition_apps_by_word(
    preview: PushPreview,
    *,
    max_additions: int = PUSH_SMALL_DELTA_REVIEW_MAX,
) -> dict[str, tuple[str, ...]]:
    apps: dict[str, list[str]] = defaultdict(list)
    for target in small_delta_addition_targets(preview, max_additions=max_additions):
        for word in sorted(target.addition_words):
            apps[word].append(target.name)
    return {word: tuple(names) for word, names in apps.items()}


def format_additions_detail_summary(
    preview: PushPreview,
    *,
    max_additions: int = PUSH_SMALL_DELTA_REVIEW_MAX,
) -> str:
    reviewable = small_delta_addition_targets(preview, max_additions=max_additions)
    omitted = omitted_full_sync_addition_targets(preview, max_additions=max_additions)
    unique = len(unique_reviewable_addition_words(preview, max_additions=max_additions))
    names = ", ".join(target.name for target in reviewable) if reviewable else "no small-delta apps"
    lines = [
        f"Small-delta additions across {names}: {unique} unique word(s)",
        f"(apps with more than {max_additions} additions are treated as full sync and omitted)",
    ]
    if omitted:
        omitted_names = ", ".join(target.name for target in omitted)
        lines.append(f"Omitted full sync: {omitted_names}")
    return "\n".join(lines)


def format_additions_detail_body(
    preview: PushPreview,
    *,
    max_additions: int = PUSH_SMALL_DELTA_REVIEW_MAX,
) -> str:
    by_word = addition_apps_by_word(preview, max_additions=max_additions)
    if not by_word:
        omitted = omitted_full_sync_addition_targets(preview, max_additions=max_additions)
        if omitted:
            return (
                "No small-delta additions to list.\n"
                "Large full-sync dumps into apps are omitted from this view."
            )
        return "No words planned for addition."
    lines: list[str] = []
    ordered = sorted(by_word)
    total = len(ordered)
    for index, word in enumerate(ordered, start=1):
        apps = ", ".join(by_word[word])
        lines.append(f"{numbered_word_prefix(index, total)} {word}")
        lines.append(f"  {apps}")
    return "\n".join(lines)
