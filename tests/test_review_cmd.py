"""review command and interactive removal prompts."""

import unittest
from unittest.mock import MagicMock, patch

import spell_sync.removal_review as removal_mod
from tests.tui.fake_service import sample_preview


class TestReviewInteractive(unittest.TestCase):
    def test_review_removals_for_preview_non_tty(self):
        preview = sample_preview()
        with patch.object(removal_mod.sys.stdin, "isatty", return_value=False):
            self.assertTrue(removal_mod.review_removals_for_preview(preview))

    def test_review_removals_for_preview_eof(self):
        preview = sample_preview()
        with (
            patch.object(removal_mod.sys.stdin, "isatty", return_value=True),
            patch("builtins.input", side_effect=EOFError),
        ):
            self.assertIsNone(removal_mod.review_removals_for_preview(preview))

    def test_review_no_removals_returns_true(self):
        preview = sample_preview(removals=0, targets=())
        self.assertTrue(removal_mod.review_removals_for_preview(preview))

    def test_review_removals_for_preview_yes(self):
        preview = sample_preview()
        with (
            patch.object(removal_mod.sys.stdin, "isatty", return_value=True),
            patch("builtins.input", return_value="y"),
        ):
            self.assertTrue(removal_mod.review_removals_for_preview(preview))

    def test_list_removals_from_preview(self):
        preview = sample_preview()
        diffs = removal_mod.list_removals_from_preview(preview)
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0].to_remove, 1)

    def test_review_removals_for_preview_and_list(self):
        from spell_sync.application.reports import PushPreview, TargetPreview
        from spell_sync.removal_review import (
            list_removals_from_preview,
            review_removals_for_preview,
        )

        preview = PushPreview(
            prepared=MagicMock(),
            targets=(
                TargetPreview(
                    name="a",
                    additions=0,
                    removals=2,
                    status="update",
                    removal_words=frozenset({"gone", "lost"}),
                ),
            ),
            additions=0,
            removals=2,
            warnings=(),
            created_at="t",
            plan_identifier="p",
            targets_to_update=1,
            unchanged=0,
            skipped=(),
            corrupt=(),
            blocked=(),
        )
        self.assertTrue(review_removals_for_preview(preview, interactive=False))
        diffs = list_removals_from_preview(preview)
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0].to_remove, 2)
        with (
            patch("builtins.input", return_value="y"),
            patch("sys.stdin.isatty", return_value=True),
        ):
            self.assertTrue(review_removals_for_preview(preview, interactive=True))
        with (
            patch("builtins.input", side_effect=EOFError),
            patch("sys.stdin.isatty", return_value=True),
        ):
            self.assertIsNone(review_removals_for_preview(preview, interactive=True))

        empty_removals = PushPreview(
            prepared=MagicMock(),
            targets=(TargetPreview(name="a", additions=1, removals=0, status="add"),),
            additions=1,
            removals=0,
            warnings=(),
            created_at="t",
            plan_identifier="p",
            targets_to_update=1,
            unchanged=0,
            skipped=(),
            corrupt=(),
            blocked=(),
        )
        self.assertTrue(review_removals_for_preview(empty_removals, interactive=False))
        mixed_preview = PushPreview(
            prepared=MagicMock(),
            targets=(
                TargetPreview(name="a", additions=1, removals=0, status="add"),
                TargetPreview(
                    name="b",
                    additions=0,
                    removals=1,
                    status="update",
                    removal_words=frozenset({"x"}),
                ),
            ),
            additions=1,
            removals=1,
            warnings=(),
            created_at="t",
            plan_identifier="p",
            targets_to_update=1,
            unchanged=0,
            skipped=(),
            corrupt=(),
            blocked=(),
        )
        mixed = list_removals_from_preview(mixed_preview)
        self.assertEqual(len(mixed), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
