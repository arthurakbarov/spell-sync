#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SyncRun tests."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import spell_sync.log as log_module
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import read_text_words, write_text_words
from spell_sync.sync_run import PushResult, SyncRun


class TestSyncRun(unittest.TestCase):
    def setUp(self):
        log_module.log.quiet = True

    def tearDown(self):
        log_module.log.quiet = False

    def _run(self, d: str):
        wordlist = os.path.join(d, "wordlist.txt")
        path_a = os.path.join(d, "a.txt")
        path_b = os.path.join(d, "b.txt")
        dictionaries = [
            Dictionary("a", path_a, DictionaryFormat.TEXT),
            Dictionary("b", path_b, DictionaryFormat.TEXT),
        ]
        run = SyncRun(wordlist=wordlist, dictionaries=dictionaries)
        return run, wordlist, path_a, path_b

    def test_pull_unions_words(self):
        with tempfile.TemporaryDirectory() as d:
            run, wordlist, path_a, path_b = self._run(d)
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(path_a, ["beta"], "utf-8", False, quiet=True)
            write_text_words(path_b, ["gamma"], "utf-8", False, quiet=True)
            before, after = run.pull_into_wordlist()
            self.assertEqual((before, after), (1, 3))
            self.assertEqual(run.load_wordlist(), {"alpha", "beta", "gamma"})

    def test_push_overwrites_dictionaries(self):
        with tempfile.TemporaryDirectory() as d:
            run, wordlist, path_a, path_b = self._run(d)
            words = ["alpha", "beta"]
            write_text_words(wordlist, words, "utf-8", False, quiet=True)
            write_text_words(path_a, ["stale"], "utf-8", False, quiet=True)
            result = run.push_from_wordlist()
            self.assertEqual(result.word_count, 2)
            self.assertEqual(result.written, ("a", "b"))
            self.assertEqual(result.skipped, ())
            self.assertEqual(
                read_text_words(path_a, quiet=True),
                {"alpha", "beta"},
            )

    def test_push_aborts_on_empty_wordlist(self):
        with tempfile.TemporaryDirectory() as d:
            run, wordlist, _, _ = self._run(d)
            open(wordlist, "w", encoding="utf-8").close()
            self.assertEqual(run.push_from_wordlist(), ExitCode.PUSH_ABORT)

    def test_status_diffs(self):
        with tempfile.TemporaryDirectory() as d:
            run, wordlist, path_a, path_b = self._run(d)
            write_text_words(wordlist, ["alpha", "beta"], "utf-8", False, quiet=True)
            write_text_words(path_a, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(
                path_b,
                ["alpha", "beta", "extra"],
                "utf-8",
                False,
                quiet=True,
            )
            diffs = run.status_diffs()
            by_name = {diff.name: diff for diff in diffs}
            self.assertEqual(by_name["a"].to_add, 1)
            self.assertEqual(by_name["b"].to_remove, 1)

    def test_status_diffs_verbose_lists_words(self):
        with tempfile.TemporaryDirectory() as d:
            run, wordlist, path_a, path_b = self._run(d)
            write_text_words(wordlist, ["alpha", "beta"], "utf-8", False, quiet=True)
            write_text_words(path_a, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(
                path_b,
                ["alpha", "beta", "extra"],
                "utf-8",
                False,
                quiet=True,
            )
            diff_a = run.status_diffs(verbose=True)[0]
            self.assertEqual(diff_a.add_words, ("beta",))

    def test_pull_cleans_wordlist_before_count(self):
        with tempfile.TemporaryDirectory() as d:
            run, wordlist, _, _ = self._run(d)
            with open(wordlist, "w", encoding="utf-8") as handle:
                handle.write("valid\nbad word\n")
            before, after = run.pull_into_wordlist()
            self.assertEqual((before, after), (1, 1))

    def test_push_removes_extra_dictionary_words(self):
        with tempfile.TemporaryDirectory() as d:
            run, wordlist, path_a, _ = self._run(d)
            write_text_words(wordlist, ["keep"], "utf-8", False, quiet=True)
            write_text_words(
                path_a,
                ["keep", "remove"],
                "utf-8",
                False,
                quiet=True,
            )
            run.push_from_wordlist()
            self.assertEqual(read_text_words(path_a, quiet=True), {"keep"})

    def test_push_skips_unreadable_dictionary(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            path_ok = os.path.join(d, "ok.txt")
            path_blocked = os.path.join(d, "blocked.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(path_ok, ["stale"], "utf-8", False, quiet=True)
            write_text_words(
                path_blocked,
                ["blocked-stale"],
                "utf-8",
                False,
                quiet=True,
            )
            dictionaries = [
                Dictionary("ok", path_ok, DictionaryFormat.TEXT),
                Dictionary("blocked", path_blocked, DictionaryFormat.TEXT),
            ]
            run = SyncRun(wordlist=wordlist, dictionaries=dictionaries)

            def readable(path):
                return str(path) != path_blocked

            patch_target = "spell_sync.read_outcome.is_path_readable"
            with patch(patch_target, side_effect=lambda p: readable(p)):
                result = run.push_from_wordlist()
            self.assertEqual(result.word_count, 1)
            self.assertEqual(result.written, ("ok",))
            self.assertEqual(result.skipped, ("blocked",))
            self.assertEqual(read_text_words(path_ok, quiet=True), {"alpha"})
            self.assertEqual(
                read_text_words(path_blocked, quiet=True),
                {"blocked-stale"},
            )

    def test_push_returns_partial_when_all_dictionaries_unreadable(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            path_a = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(path_a, ["stale"], "utf-8", False, quiet=True)
            dict_a = Dictionary("a", path_a, DictionaryFormat.TEXT)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[dict_a],
            )
            with patch("spell_sync.read_outcome.is_path_readable", return_value=False):
                result = run.push_from_wordlist()
            self.assertIsInstance(result, PushResult)
            assert not isinstance(result, ExitCode)
            self.assertEqual(result.written, ())
            self.assertEqual(result.skipped, ("a",))
            self.assertEqual(read_text_words(path_a, quiet=True), {"stale"})

    def test_pull_aborts_when_wordlist_write_fails(self):
        with tempfile.TemporaryDirectory() as d:
            run, wordlist, path_a, _ = self._run(d)
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(path_a, ["beta"], "utf-8", False, quiet=True)
            with patch.object(run, "_write_wordlist", return_value=False):
                result = run.pull_into_wordlist()
            self.assertEqual(result, ExitCode.PUSH_ABORT)
            self.assertEqual(run.load_wordlist(), {"alpha"})


class TestSyncRunEdgeCases(unittest.TestCase):
    def setUp(self):
        log_module.log.quiet = True

    def tearDown(self):
        log_module.log.quiet = False

    def test_status_skips_corrupt_dictionary(self):
        import io
        from contextlib import redirect_stdout

        log_module.log.quiet = False
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            bad = os.path.join(d, "bad.xml")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            Path(bad).write_text("<broken", encoding="utf-8")
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[
                    Dictionary(
                        "jetbrains:IDEA",
                        bad,
                        DictionaryFormat.JETBRAINS,
                    ),
                ],
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                diffs = run.status_diffs()
            self.assertEqual(diffs, [])
            self.assertIn("corrupt or unsupported", buf.getvalue())

    def test_save_wordlist_writes_sorted_merged_words(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            self.assertTrue(run.save_wordlist({"Beta", "alpha"}))
            self.assertEqual(read_text_words(wordlist, quiet=True), {"Beta", "alpha"})

    def test_status_skips_unreadable_dictionary(self):
        import io
        from contextlib import redirect_stdout

        log_module.log.quiet = False
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(dict_path, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            buf = io.StringIO()
            with (
                patch("spell_sync.read_outcome.is_path_readable", return_value=False),
                redirect_stdout(buf),
            ):
                diffs = run.status_diffs()
            self.assertEqual(diffs, [])
            self.assertIn("diff skipped", buf.getvalue())

    def test_status_skips_unreadable_dictionary_quiet(self):
        import io
        from contextlib import redirect_stdout

        log_module.log.quiet = False
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(dict_path, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            buf = io.StringIO()
            with (
                patch("spell_sync.read_outcome.is_path_readable", return_value=False),
                redirect_stdout(buf),
            ):
                diffs = run.status_diffs(quiet_unreadable=True)
            self.assertEqual(diffs, [])
            self.assertNotIn("diff skipped", buf.getvalue())

    def test_pull_skips_corrupt_dictionary(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            good = os.path.join(d, "good.txt")
            bad = os.path.join(d, "bad.xml")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(good, ["beta"], "utf-8", False, quiet=True)
            Path(bad).write_text("<broken", encoding="utf-8")
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[
                    Dictionary("good", good, DictionaryFormat.TEXT),
                    Dictionary(
                        "jetbrains:IDEA",
                        bad,
                        DictionaryFormat.JETBRAINS,
                    ),
                ],
            )
            before, after = run.pull_into_wordlist()
            self.assertEqual((before, after), (1, 2))
            self.assertEqual(run.load_wordlist(), {"alpha", "beta"})
            self.assertEqual(Path(bad).read_text(encoding="utf-8"), "<broken")

    def test_push_aborts_when_wordlist_rewrite_fails(self):

        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(dict_path, ["stale"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            with (
                patch("spell_sync.push_setup.wordlist_needs_rewrite", return_value=True),
                patch("spell_sync.push_prepared.write_rendered", return_value=False),
            ):
                result = run.push_from_wordlist()
            self.assertEqual(result, ExitCode.PUSH_ABORT)
            self.assertEqual(read_text_words(dict_path, quiet=True), {"stale"})

    def test_wordlist_needs_rewrite_when_missing(self):
        from spell_sync.push_setup import wordlist_needs_rewrite

        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            self.assertTrue(wordlist_needs_rewrite(run.context, {"alpha"}))

    def test_setup_push_returns_unreadable(self):
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            path = Path(wordlist)
            path.write_text("alpha\n", encoding="utf-8")
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            with patch("spell_sync.push_setup.wordlist_unreadable", return_value=True):
                self.assertEqual(run.check_wordlist(), ExitCode.WORDLIST_UNREADABLE)

    def test_push_aborts_on_empty_wordlist_in_setup(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            open(wordlist, "w", encoding="utf-8").close()
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            self.assertEqual(run.push_from_wordlist(), ExitCode.PUSH_ABORT)

    def test_push_aborts_when_wordlist_unreadable_in_transaction(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            run = SyncRun(wordlist=wordlist, dictionaries=[])
            with patch.object(
                run,
                "check_wordlist",
                return_value=ExitCode.WORDLIST_UNREADABLE,
            ):
                self.assertEqual(
                    run.push_from_wordlist(),
                    ExitCode.WORDLIST_UNREADABLE,
                )

    def test_push_aborts_when_wordlist_backup_fails(self):
        from unittest.mock import MagicMock

        import spell_sync.push_transaction as push_tx_mod

        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(dict_path, ["stale"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            mock_tx = MagicMock()
            mock_tx.wordlist_backup.existed_before = True
            mock_tx.wordlist_backup.backup = None
            with patch.object(push_tx_mod.PushTransaction, "begin", return_value=mock_tx):
                result = run.push_from_wordlist()
            self.assertEqual(result, ExitCode.PUSH_ABORT)
            mock_tx.close.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
