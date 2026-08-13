"""Tests for central product copy."""

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

    def test_push_scope_and_preview_context(self):
        scope = pc.PUSH_SCOPE_NOTICE.lower()
        self.assertIn("applicable personal", scope)
        self.assertIn("custom diction", scope)
        context = pc.PUSH_PREVIEW_CONTEXT.lower()
        self.assertIn("most apps", context)
        self.assertIn("filtered", context)
        self.assertIn("duplicate custom entries", context)
        self.assertNotIn("every target receives the full canonical wordlist", scope)

    def test_push_redundancy_uses_personal_wordlist_consistency(self):
        lowered = pc.PUSH_REDUNDANCY_NOTICE.lower()
        self.assertIn("personal word list", lowered)
        self.assertIn("built-in", lowered)
        self.assertNotIn("keeps applications consistent", lowered)
        self.assertNotIn("keeps enabled applications consistent", lowered)

    def test_built_in_dictionaries_are_excluded(self):
        for text in (
            pc.CUSTOM_DICTIONARY_SCOPE_NOTICE,
            pc.WELCOME_BUILT_IN_EXCLUSION,
            pc.APPLICATIONS_SCOPE_NOTICE,
            pc.PUSH_REDUNDANCY_NOTICE,
            pc.CLI_ROOT_DESCRIPTION,
        ):
            lowered = text.lower()
            self.assertIn("built-in", lowered)
            self.assertTrue(
                "not inspect" in lowered
                or "does not inspect" in lowered
                or "not modified" in lowered
                or "never read" in lowered
                or "never changed" in lowered,
                msg=text,
            )

    def test_pull_preview_additions_line(self):
        self.assertIn("from your apps", pc.pull_preview_additions_line(3).lower())
        self.assertIn("already", pc.pull_preview_additions_line(0).lower())

    def test_report_summaries(self):
        self.assertIn("custom diction", pc.pull_completed_summary(2).lower())
        summary = pc.push_completed_summary(2).lower()
        self.assertIn("custom diction", summary)
        self.assertIn("updated from your word list", summary)
        self.assertNotIn("was written to", summary)
        self.assertIn("no new personal", pc.pull_completed_summary(0).lower())
        self.assertIn("no custom diction", pc.push_completed_summary(0).lower())
        self.assertIn("1 word from your apps is", pc.pull_preview_additions_line(1).lower())

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
