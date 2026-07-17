#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for subprocess helpers."""

from __future__ import annotations

import unittest

from spell_sync.subprocess_utils import trim_subprocess_text


class TestTrimSubprocessText(unittest.TestCase):
    def test_empty_and_whitespace(self):
        self.assertEqual(trim_subprocess_text(""), "")
        self.assertEqual(trim_subprocess_text("   \n\t "), "")

    def test_no_trim_under_limit(self):
        self.assertEqual(trim_subprocess_text("boom", limit=10), "boom")

    def test_trims_and_marks(self):
        out = trim_subprocess_text("x" * 20, limit=10)
        self.assertTrue(out.startswith("x" * 10))
        self.assertIn("[truncated]", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
