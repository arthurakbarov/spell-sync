#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""review command and interactive removal prompts."""

import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
