"""Safety regressions for TUI mutation facade over real core."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from spell_sync.application.builders import build_pull_preview, build_push_preview
from spell_sync.application.reports import OperationOutcome
from spell_sync.application.service import SpellSyncService
from spell_sync.cli_options import CliOptions
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import read_text_words
from spell_sync.sync_run import SyncRun


class TestTuiMutationSafety(unittest.TestCase):
    def _project(self, tmp: str) -> tuple[Path, Path, SyncRun, CliOptions]:
        root = Path(tmp)
        wordlist = root / "wordlist.txt"
        dictionary = root / "local.txt"
        wordlist.write_text("alpha\nbeta\n", encoding="utf-8")
        dictionary.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
        (root / "spell-sync.toml").write_text("[dictionaries]\neditors = false\n", encoding="utf-8")
        run = SyncRun(
            wordlist=wordlist,
            dictionaries=[Dictionary("custom", str(dictionary), DictionaryFormat.TEXT)],
        )
        opts = CliOptions(wordlist=str(wordlist))
        return wordlist, dictionary, run, opts

    def test_execute_push_preview_keeps_prepared_identity(self):
        service = SpellSyncService()
        with tempfile.TemporaryDirectory() as tmp:
            _wordlist, _dictionary, run, opts = self._project(tmp)
            prepared = service.prepare_push(run, opts)
            self.assertNotIsInstance(prepared, ExitCode)
            preview = build_push_preview(prepared)
            result = service.execute_push_preview(
                opts,
                preview,
                confirmed_plan_id=preview.plan_identifier,
            )
            self.assertIs(result.prepared, preview.prepared)
            self.assertIs(result.prepared, prepared)

    def test_fingerprint_conflict_does_not_delete_extra_words(self):
        service = SpellSyncService()
        with tempfile.TemporaryDirectory() as tmp:
            _wordlist, dictionary, run, opts = self._project(tmp)
            prepared = service.prepare_push(run, opts)
            self.assertNotIsInstance(prepared, ExitCode)
            preview = build_push_preview(prepared)
            self.assertEqual(preview.removals, 1)
            extra = [f"extra{i}" for i in range(60)]
            dictionary.write_text(
                "alpha\nbeta\ngamma\n" + "\n".join(extra) + "\n",
                encoding="utf-8",
            )
            execution = service.execute_push_preview(
                opts,
                preview,
                confirmed_plan_id=preview.plan_identifier,
            )
            self.assertEqual(execution.outcome, OperationOutcome.STOPPED_SAFELY)
            self.assertIsNotNone(execution.conflict_target)
            words = read_text_words(dictionary)
            self.assertGreaterEqual(len(words), 60)
            self.assertIn("extra0", words)

    def test_pull_preview_execute_writes_prepared_merge(self):
        service = SpellSyncService()
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, dictionary, run, opts = self._project(tmp)
            dictionary.write_text("alpha\nbeta\ndelta\n", encoding="utf-8")
            preview = build_pull_preview(run)
            self.assertEqual(preview.additions, 1)
            self.assertIn("delta", preview.addition_words)
            execution = service.execute_pull(
                opts,
                preview,
                confirmed_plan_id=preview.plan_identifier,
            )
            self.assertEqual(execution.outcome, OperationOutcome.COMPLETED)
            words = read_text_words(wordlist)
            self.assertIn("delta", words)

    def test_pull_plan_id_mismatch_rejects_execution(self):
        service = SpellSyncService()
        with tempfile.TemporaryDirectory() as tmp:
            _wordlist, _dictionary, run, opts = self._project(tmp)
            preview = build_pull_preview(run)
            execution = service.execute_pull(
                opts,
                preview,
                confirmed_plan_id="not-the-plan",
            )
            self.assertEqual(execution.result, ExitCode.PUSH_ABORT)
            self.assertEqual(execution.outcome, OperationOutcome.FAILED)


if __name__ == "__main__":
    unittest.main()
