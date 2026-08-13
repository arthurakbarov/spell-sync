"""Unique addition/removal preview summary copy."""

import unittest

from spell_sync.application.product_concepts import PUSH_PREVIEW_CONTEXT
from spell_sync.application.push_preview_copy import (
    format_additions_confirm_counts,
    format_additions_detail_body,
    format_additions_detail_summary,
    format_push_preview_summary,
    format_removals_confirm_counts,
    format_removals_confirm_sentence,
    format_removals_detail_body,
    format_removals_detail_summary,
    format_words_to_add_line,
    format_words_to_remove_line,
    push_detail_buttons_visible,
    unique_addition_words,
    unique_removal_words,
    unique_reviewable_addition_words,
)
from spell_sync.application.reports import TargetPreview
from spell_sync.config import PUSH_SMALL_DELTA_REVIEW_MAX
from tests.tui.fake_service import sample_preview


def _preview_with_overlap() -> object:
    return sample_preview(
        targets=(
            TargetPreview(
                name="sublime",
                additions=0,
                removals=3,
                status="Review",
                removal_words=frozenset({"Huawei", "Jupyter", "Netflix"}),
            ),
            TargetPreview(
                name="macos",
                additions=0,
                removals=2,
                status="Review",
                removal_words=frozenset({"Huawei", "Sokoban"}),
            ),
            TargetPreview(
                name="nvim",
                additions=0,
                removals=2,
                status="Review",
                removal_words=frozenset({"Netflix", "Sokoban"}),
            ),
        ),
        removals=7,
        additions=0,
        targets_to_update=3,
    )


class TestPushPreviewCopy(unittest.TestCase):
    def test_overlap_summary_uses_unique_counts_only(self) -> None:
        preview = _preview_with_overlap()
        self.assertEqual(len(unique_removal_words(preview)), 4)
        self.assertEqual(format_words_to_remove_line(preview), "Words to remove: 4")
        self.assertEqual(
            format_removals_detail_summary(target_label="sublime, macos, nvim", preview=preview),
            "Removals across sublime, macos, nvim: 4 word(s)",
        )
        self.assertEqual(format_removals_confirm_sentence(preview), "4 words")
        self.assertEqual(format_removals_confirm_counts(preview), "4 removals")

    def test_addition_summary_uses_unique_not_sum(self) -> None:
        shared = frozenset({"alpha", "beta", "gamma"})
        preview = sample_preview(
            targets=(
                TargetPreview(
                    name="vscode",
                    additions=3,
                    removals=0,
                    status="Ready",
                    addition_words=shared,
                ),
                TargetPreview(
                    name="chrome",
                    additions=3,
                    removals=0,
                    status="Ready",
                    addition_words=shared,
                ),
                TargetPreview(
                    name="sublime",
                    additions=1,
                    removals=0,
                    status="Ready",
                    addition_words=frozenset({"delta"}),
                ),
            ),
            additions=7,
            removals=0,
            targets_to_update=3,
        )
        self.assertEqual(len(unique_addition_words(preview)), 4)
        self.assertEqual(format_words_to_add_line(preview), "Words to add: 4")
        self.assertEqual(format_additions_confirm_counts(preview), "4 additions")

    def test_detail_body_lists_apps_per_word(self) -> None:
        preview = _preview_with_overlap()
        body = format_removals_detail_body(preview)
        self.assertIn("Huawei\n  sublime, macos", body)
        self.assertIn("Sokoban\n  macos, nvim", body)

    def test_no_overlap_stays_simple(self) -> None:
        preview = sample_preview(
            targets=(
                TargetPreview(
                    name="sublime",
                    additions=0,
                    removals=2,
                    status="Review",
                    removal_words=frozenset({"alpha", "beta"}),
                ),
            ),
            removals=2,
        )
        self.assertEqual(format_words_to_remove_line(preview), "Words to remove: 2")
        self.assertEqual(
            format_removals_detail_summary(target_label="sublime", preview=preview),
            "Removals across sublime: 2 word(s)",
        )

    def test_addition_review_omits_full_sync_dumps(self) -> None:
        small = frozenset({"delta", "epsilon"})
        huge = frozenset({f"w{i}" for i in range(PUSH_SMALL_DELTA_REVIEW_MAX + 10)})
        preview = sample_preview(
            targets=(
                TargetPreview(
                    name="sublime",
                    additions=len(small),
                    removals=0,
                    status="Ready",
                    addition_words=small,
                ),
                TargetPreview(
                    name="chrome",
                    additions=len(huge),
                    removals=0,
                    status="Ready",
                    addition_words=huge,
                ),
            ),
            additions=len(small) + len(huge),
            removals=0,
            targets_to_update=2,
        )
        self.assertEqual(unique_reviewable_addition_words(preview), small)
        has_additions, has_removals = push_detail_buttons_visible(preview)
        self.assertTrue(has_additions)
        self.assertFalse(has_removals)
        empty = sample_preview(
            additions=0,
            removals=0,
            targets_to_update=0,
            targets=(TargetPreview("chrome", 0, 0, "Unchanged"),),
        )
        self.assertEqual(push_detail_buttons_visible(empty), (False, False))
        summary = format_additions_detail_summary(preview)
        self.assertIn("2 unique word(s)", summary)
        self.assertIn("Omitted full sync: chrome", summary)
        body = format_additions_detail_body(preview)
        self.assertIn("delta\n  sublime", body)
        self.assertNotIn("w0", body)

    def test_summary_includes_counts_and_preview_context(self) -> None:
        preview = sample_preview(skipped=("offline",), warnings=("watch",))
        summary = format_push_preview_summary(preview)
        self.assertIn("Words to add", summary)
        self.assertIn("Skipped: offline", summary)
        self.assertIn("! Warnings: watch", summary)
        self.assertIn(PUSH_PREVIEW_CONTEXT.splitlines()[0], summary)
        self.assertIn("duplicate custom entries", summary.lower())
        # Field contract: ":" glued to key; values share one column.
        self.assertIn("\n\nYour word list", summary)
        count_block = [
            line
            for line in summary.splitlines()
            if line.split(":", 1)[0].strip()
            in {
                "Dictionaries to update",
                "Words to add",
                "Words to remove",
                "Unchanged",
            }
        ]
        self.assertEqual(len(count_block), 4)
        self.assertTrue(all(": " in line or line.rstrip().endswith(":") for line in count_block))
        value_cols = set()
        for line in count_block:
            colon = line.index(":")
            i = colon + 1
            while i < len(line) and line[i] == " ":
                i += 1
            value_cols.add(i)
        self.assertEqual(len(value_cols), 1, count_block)


if __name__ == "__main__":
    unittest.main()
