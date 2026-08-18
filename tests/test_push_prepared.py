"""execute_prepared_push branch coverage: journal faults, fingerprints, aborts."""

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import write_text_words
from spell_sync.push_abort import PushAbort
from spell_sync.push_journal import PushJournalSession
from spell_sync.push_prepared import execute_prepared_push
from spell_sync.push_render import RenderedWrite, render_wordlist
from spell_sync.sync_run import PushResult
from tests.runtime_helpers import make_sync_run


class TestPushPreparedCoverage(unittest.TestCase):
    def test_wordlist_write_and_journal_faults(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            wordlist.write_text("old\n", encoding="utf-8")
            dict_path.write_text("old\n", encoding="utf-8")
            run = make_sync_run(
                str(wordlist),
                dictionaries=[Dictionary("d", str(dict_path), DictionaryFormat.TEXT)],
            )
            prepared = run.prepare_push_operation()
            assert not isinstance(prepared, ExitCode)
            with patch(
                "spell_sync.push_prepared.write_rendered",
                side_effect=lambda path, rendered, *, settings, **kwargs: path.name != "dict.txt",
            ):
                result = execute_prepared_push(
                    prepared,
                    execution_context=prepared.ctx,
                    dry_run=False,
                    running_app_skip_reasons_fn=lambda _names: {},
                )
            self.assertIsInstance(result, PushAbort)
            self.assertEqual(result.exit_code, ExitCode.PUSH_ABORT)

    def test_fingerprint_during_write_and_complete_fault(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            write_text_words(str(wordlist), ["a"], "utf-8", False, quiet=True)
            write_text_words(str(dict_path), ["a"], "utf-8", False, quiet=True)
            run = make_sync_run(
                str(wordlist),
                dictionaries=[Dictionary("d", str(dict_path), DictionaryFormat.TEXT)],
            )
            prepared = run.prepare_push_operation()
            assert not isinstance(prepared, ExitCode)
            with (
                patch(
                    "spell_sync.push_prepared.write_rendered",
                    return_value=True,
                ),
                patch.object(PushJournalSession, "complete", side_effect=OSError("nope")),
            ):
                result = execute_prepared_push(
                    prepared,
                    execution_context=prepared.ctx,
                    dry_run=False,
                    running_app_skip_reasons_fn=lambda _names: {},
                )
            self.assertIsInstance(result, PushAbort)
            self.assertEqual(result.reason, "journal_update_failed")

    def test_journal_begin_failure_returns_abort(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            write_text_words(str(wordlist), ["a"], "utf-8", False, quiet=True)
            write_text_words(str(dict_path), ["a"], "utf-8", False, quiet=True)
            run = make_sync_run(
                str(wordlist),
                dictionaries=[Dictionary("d", str(dict_path), DictionaryFormat.TEXT)],
            )
            prepared = run.prepare_push_operation()
            assert not isinstance(prepared, ExitCode)
            with patch.object(PushJournalSession, "begin", side_effect=OSError("journal begin")):
                result = execute_prepared_push(
                    prepared,
                    execution_context=prepared.ctx,
                    dry_run=False,
                    running_app_skip_reasons_fn=lambda _names: {},
                )
            self.assertIsInstance(result, PushAbort)
            self.assertEqual(result.reason, "journal_begin_failed")


class TestPushPreparedWordlistPath(unittest.TestCase):
    def test_wordlist_write_journal_io_errors(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            wordlist.write_text("stale\n", encoding="utf-8")
            dict_path.write_text("stale\n", encoding="utf-8")
            run = make_sync_run(
                str(wordlist),
                dictionaries=[Dictionary("d", str(dict_path), DictionaryFormat.TEXT)],
            )
            prepared = run.prepare_push_operation()
            assert not isinstance(prepared, ExitCode)
            prepared = replace(
                prepared,
                wordlist_needs_write=True,
                wordlist_rendered=RenderedWrite(b"new\n", "a" * 64),
            )
            with patch.object(
                PushJournalSession,
                "mark_wordlist_write_started",
                side_effect=OSError("nope"),
            ):
                result = execute_prepared_push(
                    prepared,
                    execution_context=prepared.ctx,
                    dry_run=False,
                    running_app_skip_reasons_fn=lambda _names: {},
                )
            self.assertIsInstance(result, PushAbort)
            self.assertEqual(result.reason, "journal_update_failed")

    def test_per_dictionary_journal_io_and_fingerprint_mid_write(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            write_text_words(str(wordlist), ["a", "b"], "utf-8", False, quiet=True)
            write_text_words(str(dict_path), ["a", "b"], "utf-8", False, quiet=True)
            run = make_sync_run(
                str(wordlist),
                dictionaries=[Dictionary("d", str(dict_path), DictionaryFormat.TEXT)],
            )
            prepared = run.prepare_push_operation()
            assert not isinstance(prepared, ExitCode)
            with patch.object(
                PushJournalSession,
                "mark_write_started",
                side_effect=OSError("nope"),
            ):
                result = execute_prepared_push(
                    prepared,
                    execution_context=prepared.ctx,
                    dry_run=False,
                    running_app_skip_reasons_fn=lambda _names: {},
                )
            self.assertIsInstance(result, PushAbort)


class TestPushPreparedRemainingBranches(unittest.TestCase):
    def test_write_rendered_oserror_and_early_fingerprint(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            write_text_words(str(wordlist), ["a"], "utf-8", False, quiet=True)
            write_text_words(str(dict_path), ["a"], "utf-8", False, quiet=True)
            run = make_sync_run(
                str(wordlist),
                dictionaries=[Dictionary("d", str(dict_path), DictionaryFormat.TEXT)],
            )
            prepared = run.prepare_push_operation()
            assert not isinstance(prepared, ExitCode)
            write_text_words(str(dict_path), ["changed"], "utf-8", False, quiet=True)
            result = execute_prepared_push(
                prepared,
                execution_context=prepared.ctx,
                dry_run=False,
                running_app_skip_reasons_fn=lambda _names: {},
            )
            self.assertEqual(result, ExitCode.PUSH_ABORT)
            with patch("spell_sync.push_prepared.atomic_write", side_effect=OSError("nope")):
                prepared2 = run.prepare_push_operation()
                assert not isinstance(prepared2, ExitCode)
                result2 = execute_prepared_push(
                    prepared2,
                    execution_context=prepared2.ctx,
                    dry_run=False,
                    running_app_skip_reasons_fn=lambda _names: {},
                )
            self.assertIsInstance(result2, PushAbort)

    def test_wordlist_write_success_path(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            wordlist.write_text("stale\n", encoding="utf-8")
            write_text_words(str(dict_path), ["a"], "utf-8", False, quiet=True)
            run = make_sync_run(
                str(wordlist),
                dictionaries=[Dictionary("d", str(dict_path), DictionaryFormat.TEXT)],
            )
            prepared = run.prepare_push_operation()
            assert not isinstance(prepared, ExitCode)
            rendered = render_wordlist(prepared.words)
            prepared = replace(
                prepared,
                wordlist_needs_write=True,
                wordlist_rendered=rendered,
            )
            result = execute_prepared_push(
                prepared,
                execution_context=prepared.ctx,
                dry_run=False,
                running_app_skip_reasons_fn=lambda _names: {},
            )
            self.assertIsInstance(result, PushResult)

    def test_wordlist_write_render_fail_and_journal_complete_oserror(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            wordlist.write_text("stale\n", encoding="utf-8")
            write_text_words(str(dict_path), ["a"], "utf-8", False, quiet=True)
            run = make_sync_run(
                str(wordlist),
                dictionaries=[Dictionary("d", str(dict_path), DictionaryFormat.TEXT)],
            )
            prepared = run.prepare_push_operation()
            assert not isinstance(prepared, ExitCode)
            rendered = render_wordlist(prepared.words)
            prepared = replace(
                prepared,
                wordlist_needs_write=True,
                wordlist_rendered=rendered,
            )
            with patch(
                "spell_sync.push_prepared.write_rendered",
                side_effect=lambda path, payload, *, settings, **kwargs: (
                    path.name != "wordlist.txt"
                ),
            ):
                result = execute_prepared_push(
                    prepared,
                    execution_context=prepared.ctx,
                    dry_run=False,
                    running_app_skip_reasons_fn=lambda _names: {},
                )
            self.assertIsInstance(result, PushAbort)
            prepared2 = replace(
                run.prepare_push_operation(),
                wordlist_needs_write=True,
                wordlist_rendered=rendered,
            )
            assert not isinstance(prepared2, ExitCode)
            with (
                patch("spell_sync.push_prepared.write_rendered", return_value=True),
                patch.object(
                    PushJournalSession,
                    "mark_wordlist_write_completed",
                    side_effect=OSError("nope"),
                ),
            ):
                result2 = execute_prepared_push(
                    prepared2,
                    execution_context=prepared2.ctx,
                    dry_run=False,
                    running_app_skip_reasons_fn=lambda _names: {},
                )
            self.assertIsInstance(result2, PushAbort)

    def test_mid_write_fingerprint_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            write_text_words(str(wordlist), ["a"], "utf-8", False, quiet=True)
            write_text_words(str(dict_path), ["a"], "utf-8", False, quiet=True)
            run = make_sync_run(
                str(wordlist),
                dictionaries=[Dictionary("d", str(dict_path), DictionaryFormat.TEXT)],
            )
            prepared = run.prepare_push_operation()
            assert not isinstance(prepared, ExitCode)
            from spell_sync.push_plan import fingerprint_conflict as real_fp

            calls = {"n": 0}

            def second_pass_conflict(dictionary, read_result):
                calls["n"] += 1
                if calls["n"] >= 2:
                    return True
                return real_fp(dictionary, read_result)

            with patch(
                "spell_sync.push_prepared.fingerprint_conflict",
                side_effect=second_pass_conflict,
            ):
                result = execute_prepared_push(
                    prepared,
                    execution_context=prepared.ctx,
                    dry_run=False,
                    running_app_skip_reasons_fn=lambda _names: {},
                )
            self.assertIsInstance(result, PushAbort)
            self.assertEqual(result.reason, "fingerprint_conflict")

    def test_writable_dictionary_missing_from_prepared_targets(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            write_text_words(str(wordlist), ["a"], "utf-8", False, quiet=True)
            write_text_words(str(dict_path), ["a"], "utf-8", False, quiet=True)
            dictionary = Dictionary("d", str(dict_path), DictionaryFormat.TEXT)
            run = make_sync_run(str(wordlist), dictionaries=[dictionary])
            prepared = run.prepare_push_operation()
            assert not isinstance(prepared, ExitCode)
            prepared = replace(prepared, targets=())
            with patch("spell_sync.push_prepared.write_rendered", return_value=True):
                result = execute_prepared_push(
                    prepared,
                    execution_context=prepared.ctx,
                    dry_run=False,
                    running_app_skip_reasons_fn=lambda _names: {},
                )
            self.assertIsInstance(result, PushResult)
            self.assertEqual(result.written, ())


if __name__ == "__main__":
    unittest.main(verbosity=2)
