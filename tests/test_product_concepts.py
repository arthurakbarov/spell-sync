"""Tests for central product copy."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from spell_sync.application import product_concepts as pc


class TestProductConcepts(unittest.TestCase):
    def test_canonical_explanation_covers_personal_exceptions(self):
        combined = " ".join(
            (
                pc.CANONICAL_WORDLIST_SHORT_DESCRIPTION,
                pc.CANONICAL_WORDLIST_LONG_DESCRIPTION,
            )
        ).lower()
        self.assertIn("personal", combined)
        self.assertIn("exception", combined)

    def test_scope_notices_mention_custom_dictionaries(self):
        for text in (
            pc.CUSTOM_DICTIONARY_SCOPE_NOTICE,
            pc.PULL_SCOPE_NOTICE,
            pc.PUSH_SCOPE_NOTICE,
        ):
            self.assertIn("custom diction", text.lower())

    def test_push_scope_mentions_filtering(self):
        lowered = pc.PUSH_SCOPE_NOTICE.lower()
        self.assertIn("applicable personal", lowered)
        self.assertIn("most targets", lowered)
        self.assertIn("filter", lowered)
        self.assertNotIn("every target receives the full canonical wordlist", lowered)

    def test_push_redundancy_uses_personal_wordlist_consistency(self):
        lowered = pc.PUSH_REDUNDANCY_NOTICE.lower()
        self.assertIn("personal wordlist", lowered)
        self.assertIn("built-in", lowered)
        self.assertNotIn("keeps applications consistent", lowered)
        self.assertNotIn("keeps enabled applications consistent", lowered)

    def test_built_in_dictionaries_are_excluded(self):
        for text in (
            pc.CUSTOM_DICTIONARY_SCOPE_NOTICE,
            pc.WELCOME_BUILT_IN_EXCLUSION,
            pc.TARGETS_SCOPE_NOTICE,
            pc.PUSH_REDUNDANCY_NOTICE,
            pc.CLI_ROOT_DESCRIPTION,
        ):
            lowered = text.lower()
            self.assertIn("built-in", lowered)
            self.assertTrue(
                "not inspect" in lowered
                or "does not inspect" in lowered
                or "not modified" in lowered,
                msg=text,
            )

    def test_pull_preview_additions_line(self):
        self.assertIn("custom diction", pc.pull_preview_additions_line(3).lower())
        self.assertIn("already", pc.pull_preview_additions_line(0).lower())

    def test_report_summaries(self):
        self.assertIn("custom diction", pc.pull_completed_summary(2).lower())
        summary = pc.push_completed_summary(2).lower()
        self.assertIn("custom diction", summary)
        self.assertIn("updated from the canonical wordlist", summary)
        self.assertNotIn("was written to", summary)
        self.assertIn("no new personal", pc.pull_completed_summary(0).lower())
        self.assertIn("no custom diction", pc.push_completed_summary(0).lower())
        self.assertIn("1 word were", pc.pull_preview_additions_line(1).lower())

    def test_module_has_no_textual_or_argparse_imports(self):
        tree = ast.parse(Path(pc.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn("textual", alias.name)
                    self.assertNotIn("argparse", alias.name)
            if isinstance(node, ast.ImportFrom) and node.module:
                self.assertNotIn("textual", node.module)
                self.assertNotIn("argparse", node.module)
