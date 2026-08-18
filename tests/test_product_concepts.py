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
        self.assertIn("list is empty", pc.pull_preview_additions_line(0, before_count=0).lower())
        self.assertIn(
            "add words",
            pc.pull_preview_empty_next_line(before_count=0).lower(),
        )
        self.assertTrue(pc.pull_preview_empty_next_line(before_count=1).startswith("Next:"))
        self.assertEqual(pc.collect_confirm_add_line(1), "Add 1 word to your personal word list?")
        self.assertEqual(
            pc.collect_confirm_add_line(17), "Add 17 words to your personal word list?"
        )
        self.assertEqual(pc.words_count_label(1), "1 word")
        self.assertEqual(pc.words_count_label(2), "2 words")
        self.assertEqual(pc.numbered_word_lines({"квипва", "ываыаыа"}), "1. квипва\n2. ываыаыа")
        self.assertEqual(pc.added_words_status_block(("Acme",)), "Added (1): Acme")
        self.assertEqual(pc.added_words_status_block(("a", "b")), "Added (2): a, b")
        self.assertEqual(
            pc.added_words_status_block(("c", "a", "b")),
            "Added (3):\n1. a\n2. b\n3. c",
        )
        self.assertEqual(
            pc.pull_preview_dictionary_count_lines(ready=2, skipped=1),
            ("Dictionaries ready:   2", "Dictionaries skipped: 1"),
        )
        self.assertEqual(
            pc.pull_preview_warning_lines(("Skipped unreadable: offline",)),
            ("  ! Skipped unreadable: offline",),
        )
        self.assertEqual(
            pc.numbered_word_lines([f"w{i:02d}" for i in range(10)]),
            "\n".join(f"{index:2d}. w{index - 1:02d}" for index in range(1, 11)),
        )
        self.assertEqual(pc.COLLECT_CONFIRM_BUTTON, "Add these to my list")
        self.assertNotEqual(pc.COLLECT_CONFIRM_BUTTON, pc.COLLECT_WORDS_LABEL)
        self.assertNotEqual(pc.COLLECT_CONFIRM_BUTTON, pc.ADD_WORDS_LABEL)
        self.assertNotEqual(pc.COLLECT_CONFIRM_BUTTON, pc.EXTRA_WORDS_ADD_LABEL)
        self.assertEqual(pc.EXTRA_WORDS_SKIP_TO_REMOVE_LABEL, "Skip to remove from apps")
        self.assertEqual(pc.EXTRA_WORDS_CONTINUE_TO_REMOVE_LABEL, "Continue to remove from apps")
        self.assertIn("Update my apps", pc.EXTRA_WORDS_DONE_HINT)
        self.assertNotEqual(
            pc.EXTRA_WORDS_SKIP_TO_REMOVE_LABEL, pc.EXTRA_WORDS_CONTINUE_TO_REMOVE_LABEL
        )
        self.assertEqual(pc.CONTINUE_TO_UPDATE_APPS_LABEL, "Continue to Update my apps")
        self.assertNotEqual(pc.CONTINUE_TO_UPDATE_APPS_LABEL, pc.UPDATE_CONFIRM_BUTTON)
        self.assertEqual(pc.FIRST_WIN_COLLECT_LABEL, "Collect, then Update my apps")
        self.assertNotEqual(pc.FIRST_WIN_COLLECT_LABEL, pc.COLLECT_WORDS_LABEL)
        self.assertEqual(pc.recovery_confirm_button("recover"), "Recover files")
        self.assertEqual(pc.recovery_confirm_button("cleanup"), pc.RECOVERY_CLEANUP_LABEL)
        self.assertEqual(pc.recovery_confirm_button("discard"), pc.RECOVERY_DISCARD_LABEL)

    def test_report_summaries(self):
        self.assertIn("custom diction", pc.pull_completed_summary(2).lower())
        summary = pc.push_completed_summary(2).lower()
        self.assertIn("custom diction", summary)
        self.assertIn("updated from your word list", summary)
        self.assertIn("restart", summary)
        self.assertNotIn("was written to", summary)
        self.assertIn("no new personal", pc.pull_completed_summary(0).lower())
        self.assertIn("no custom diction", pc.push_completed_summary(0).lower())
        self.assertNotIn("restart", pc.push_completed_summary(0).lower())
        self.assertNotIn("spell-sync-words.txt", pc.push_completed_summary(2))
        self.assertIn(
            "spell-sync-words.txt",
            pc.push_completed_summary(2, editors_updated=True),
        )
        self.assertTrue(pc.written_includes_editors(("editor:cursor", "chrome:Default")))
        self.assertFalse(pc.written_includes_editors(("chrome:Default",)))
        self.assertIn("1 word from your apps is", pc.pull_preview_additions_line(1).lower())

    def test_pull_word_count_line(self):
        self.assertEqual(pc.format_pull_word_count_line(10, 12), "word list: 10 -> 12 (+2)")
        self.assertEqual(
            pc.format_pull_word_count_line(10, 12, skipped_sources=1),
            "word list: 10 -> 12 (+2); skipped 1 source",
        )
        self.assertEqual(
            pc.format_pull_word_count_line(10, 12, skipped_sources=2),
            "word list: 10 -> 12 (+2); skipped 2 sources",
        )

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
