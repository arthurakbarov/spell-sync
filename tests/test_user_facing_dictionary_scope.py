"""User-facing dictionary scope and CLI transparency tests."""

import tempfile
import unittest
from pathlib import Path

from spell_sync.application.builders import build_pull_operation_report, build_push_operation_report
from spell_sync.application.product_concepts import (
    CLI_ROOT_DESCRIPTION,
    PUSH_PREVIEW_CONTEXT,
    PUSH_SCOPE_NOTICE,
)
from spell_sync.application.reports import OperationOutcome, PullExecution, PushExecution
from spell_sync.cli import _build_parser
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.sync_models import PushResult
from spell_sync.words import subset_english, subset_russian
from tests.runtime_helpers import make_sync_run
from tests.tui.fake_service import sample_preview, sample_pull_preview

USER_FACING_FILES = (
    Path("README.md"),
    Path("docs/CONFIGURATION.md"),
    Path("docs/GETTING_STARTED.md"),
    Path("docs/SUPPORTED_APPS.md"),
    Path("spell_sync/application/product_concepts.py"),
)

DANGEROUS_UNQUALIFIED = (
    "sync built-in dictionaries",
    "copy built-in dictionaries",
    "all application dictionaries",
    "complete application dictionary",
    "words missing from application dictionaries",
    "every target receives the full canonical wordlist",
    "keeps applications consistent",
    "keeps enabled applications consistent",
)


class TestUserFacingDictionaryScope(unittest.TestCase):
    def test_cli_root_help_mentions_custom_dictionaries(self):
        parser = _build_parser()
        self.assertIn("custom diction", CLI_ROOT_DESCRIPTION.lower())
        help_text = parser.format_help()
        self.assertIn("custom diction", help_text.lower())
        self.assertIn("built-in", help_text.lower())

    def test_pull_and_push_help_direction(self):
        parser = _build_parser()
        help_text = parser.format_help().lower()
        self.assertIn("pull (collect my words)", help_text)
        self.assertIn("custom diction", help_text)
        self.assertIn("push (update my apps)", help_text)
        self.assertIn("personal words", help_text)
        self.assertNotIn("sync built-in", help_text)

    def test_push_scope_copy_matches_filtering_model(self):
        scope = PUSH_SCOPE_NOTICE.lower()
        self.assertIn("applicable personal", scope)
        context = PUSH_PREVIEW_CONTEXT.lower()
        self.assertIn("most apps", context)
        self.assertIn("filtered", context)

    def test_pull_report_summary_uses_custom_dictionaries(self):
        preview = sample_pull_preview(additions=3)
        report = build_pull_operation_report(
            PullExecution(
                preview=preview,
                result=(preview.before_count, preview.after_count),
                outcome=OperationOutcome.COMPLETED,
                message="ok",
            )
        )
        self.assertIn("custom diction", report.summary.lower())
        self.assertIn("personal", report.summary.lower())

    def test_push_report_summary_uses_custom_dictionaries(self):
        preview = sample_preview()
        report = build_push_operation_report(
            PushExecution(
                prepared=preview.prepared,
                push_preview=preview,
                result=PushResult(word_count=1, written=("custom",)),
                outcome=OperationOutcome.COMPLETED,
                message="ok",
            )
        )
        summary = report.summary.lower()
        self.assertIn("custom diction", summary)
        self.assertIn("updated from your word list", summary)
        self.assertNotIn("was written to", summary)

    def test_push_writes_to_custom_dictionary_without_built_in_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            custom = root / "custom.txt"
            wordlist.write_text("PersonalTerm\n", encoding="utf-8")
            custom.write_text("Other\n", encoding="utf-8")
            run = make_sync_run(
                wordlist,
                dictionaries=[Dictionary("custom", str(custom), DictionaryFormat.TEXT)],
            )
            result = run.push_from_wordlist()
            self.assertIsInstance(result, PushResult)
            self.assertIn("PersonalTerm", custom.read_text(encoding="utf-8"))

    def test_redundant_word_remains_in_custom_dictionary_after_push(self):
        """Word only in canonical list is written to custom storage; no removal optimization."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            custom = root / "custom.txt"
            # Simulates a word the app may already know via built-in dictionary (fixture only).
            wordlist.write_text("RedundantExample\n", encoding="utf-8")
            custom.write_text("", encoding="utf-8")
            run = make_sync_run(
                wordlist,
                dictionaries=[Dictionary("custom", str(custom), DictionaryFormat.TEXT)],
            )
            prepared = run.prepare_push_operation()
            assert not isinstance(prepared, int)
            run.push_from_wordlist(prepared=prepared)
            self.assertIn("RedundantExample", custom.read_text(encoding="utf-8"))

    def test_ordinary_target_receives_full_wordlist(self):
        words = {"alpha", "Бета", "123"}
        target = Dictionary("custom", "/tmp/custom.txt", DictionaryFormat.TEXT)
        self.assertEqual(target.target_words(words), words)

    def test_windows_english_targets_receive_latin_subset(self):
        words = {"alpha", "Бета", "123"}
        for name in ("win-en", "win-en-gb"):
            target = Dictionary(name, "/tmp/win.txt", DictionaryFormat.TEXT, subset=subset_english)
            self.assertEqual(target.target_words(words), {"alpha"})

    def test_windows_russian_target_receives_cyrillic_subset(self):
        words = {"alpha", "Бета", "123"}
        target = Dictionary("win-ru", "/tmp/win.txt", DictionaryFormat.TEXT, subset=subset_russian)
        self.assertEqual(target.target_words(words), {"Бета", "123"})

    def test_user_facing_docs_avoid_dangerous_unqualified_claims(self):
        root = Path(__file__).resolve().parents[1]
        for rel in USER_FACING_FILES:
            text = (root / rel).read_text(encoding="utf-8").lower()
            for phrase in DANGEROUS_UNQUALIFIED:
                if phrase in text:
                    # Allow only when explicitly negated in the same sentence window.
                    idx = text.index(phrase)
                    window = text[max(0, idx - 80) : idx + len(phrase) + 80]
                    self.assertTrue(
                        "not " in window or "never " in window or "does not " in window,
                        msg=f"{rel} contains unqualified {phrase!r}",
                    )


if __name__ == "__main__":
    unittest.main()
