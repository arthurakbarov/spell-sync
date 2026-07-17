#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Push journal and recover command tests."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import spell_sync.commands as commands
import spell_sync.doctor as doctor_mod
import spell_sync.recover_cmd as recover_mod
from spell_sync.cli_options import CliOptions
from spell_sync.command_helpers import mutating_command_scope, unfinished_journal_exit
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import write_text_words
from spell_sync.operation_lock import OperationLocked, OperationLockInfo, lock_path_for_wordlist
from spell_sync.push_journal import (
    JOURNAL_SCHEMA_VERSION,
    JOURNAL_STATE_WRITING,
    JournalTarget,
    PushJournal,
    PushJournalSession,
    RecoverResult,
    discard_journal,
    file_content_hash,
    journal_path_for_wordlist,
    journal_payload,
    load_push_journal,
    recover_from_journal,
)
from spell_sync.push_transaction import PushTransaction, txn_snapshot_root
from spell_sync.sync_run import PushResult, SyncRun
from tests.journal_test_utils import write_restore_scenario_journal, write_test_journal


def _locked_patch(wordlist: Path):
    info = OperationLockInfo(99, "2026-01-01T00:00:00+00:00", "push", str(wordlist))
    lock_path = lock_path_for_wordlist(wordlist)
    return patch(
        "spell_sync.command_helpers.acquire_operation_lock",
        side_effect=OperationLocked(info, lock_path),
    )


def _write_journal(wordlist: Path, *, command: str = "push") -> None:
    write_test_journal(
        wordlist,
        command=command,
        wordlist_write_started=True,
        wordlist_write_completed=True,
    )


class TestPushJournalLifecycle(unittest.TestCase):
    def test_successful_push_removes_journal(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "dict.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(dict_path, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("d", dict_path, DictionaryFormat.TEXT)],
            )
            result = run.push_from_wordlist()
            self.assertIsInstance(result, PushResult)
            self.assertFalse(journal_path_for_wordlist(Path(wordlist)).exists())

    def test_push_marks_wordlist_written_when_rewrite_needed(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            dict_path.write_text("alpha\n", encoding="utf-8")
            run = SyncRun(
                wordlist=str(wordlist),
                dictionaries=[Dictionary("d", str(dict_path), DictionaryFormat.TEXT)],
            )
            with patch("spell_sync.push_setup.wordlist_needs_rewrite", return_value=True):
                result = run.push_from_wordlist()
            self.assertIsInstance(result, PushResult)

    def test_failed_push_discards_journal(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            path_a = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["alpha", "beta"], "utf-8", False, quiet=True)
            write_text_words(path_a, ["stale"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", path_a, DictionaryFormat.TEXT)],
            )
            with patch("spell_sync.push_prepared.write_rendered", return_value=False):
                result = run.push_from_wordlist()
            self.assertEqual(result, ExitCode.PUSH_ABORT)
            self.assertFalse(journal_path_for_wordlist(Path(wordlist)).exists())

    def test_unfinished_journal_blocks_push(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            _write_journal(wordlist)
            code = commands.cmd_push(CliOptions(wordlist=str(wordlist), yes=True))
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))

    def test_unfinished_journal_json_reason(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            _write_journal(wordlist)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = commands.cmd_push(
                    CliOptions(wordlist=str(wordlist), yes=True, json_output=True),
                )
            payload = json.loads(buf.getvalue())
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))
            self.assertEqual(payload["reason"], "unfinished_transaction")
            self.assertIn("journal", payload)

    def test_recover_allowed_with_unfinished_journal(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            _write_journal(wordlist)
            with patch(
                "spell_sync.recover_cmd.recover_from_journal",
                return_value=RecoverResult((), (), ()),
            ):
                code = recover_mod.cmd_recover(
                    CliOptions(wordlist=str(wordlist), yes=True),
                )
            self.assertEqual(code, int(ExitCode.OK))


class TestRecoverCommand(unittest.TestCase):
    def test_recover_restores_from_journal_backups(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            write_restore_scenario_journal(wordlist, dict_path)

            code = recover_mod.cmd_recover(CliOptions(wordlist=str(wordlist), yes=True))
            self.assertEqual(code, int(ExitCode.OK))
            self.assertEqual(wordlist.read_text(encoding="utf-8"), "old\n")
            self.assertEqual(dict_path.read_text(encoding="utf-8"), "old\n")
            self.assertFalse(journal_path_for_wordlist(wordlist).exists())

    def test_recover_no_journal_ok(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            code = recover_mod.cmd_recover(CliOptions(wordlist=str(wordlist)))
            self.assertEqual(code, int(ExitCode.OK))

    def test_recover_non_interactive_requires_yes(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            _write_journal(wordlist)
            with patch("sys.stdin.isatty", return_value=False):
                code = recover_mod.cmd_recover(CliOptions(wordlist=str(wordlist)))
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))

    def test_recover_json_confirmation_required(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            _write_journal(wordlist)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = recover_mod.cmd_recover(
                    CliOptions(wordlist=str(wordlist), json_output=True),
                )
            payload = json.loads(buf.getvalue())
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))
            self.assertEqual(payload["reason"], "confirmation_required")

    def test_recover_dry_run_json(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("new\n", encoding="utf-8")
            transaction_id = str(__import__("uuid").uuid4())
            snap = txn_snapshot_root(wordlist, transaction_id)
            snap.mkdir(parents=True)
            bak = snap / "wordlist.snap"
            bak.write_text("old\n", encoding="utf-8")
            journal = PushJournal(
                schema_version=JOURNAL_SCHEMA_VERSION,
                transaction_id=transaction_id,
                command="push",
                pid=1,
                started="2026-01-01T00:00:00+00:00",
                state=JOURNAL_STATE_WRITING,
                wordlist=str(wordlist.resolve()),
                wordlist_hash_before=file_content_hash(bak),
                wordlist_hash_after=file_content_hash(wordlist),
                wordlist_backup_path=str(bak),
                wordlist_write_started=True,
                wordlist_write_completed=True,
                snapshot_dir=str(snap),
                targets=[],
            )
            journal_path_for_wordlist(wordlist).write_text(
                json.dumps(journal_payload(journal), indent=2) + "\n",
                encoding="utf-8",
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = recover_mod.cmd_recover(
                    CliOptions(wordlist=str(wordlist), dry_run=True, json_output=True),
                )
            payload = json.loads(buf.getvalue())
            self.assertEqual(code, int(ExitCode.OK))
            self.assertIn("wordlist", payload["restored"])
            self.assertTrue(journal_path_for_wordlist(wordlist).exists())


class TestPushJournalHelpers(unittest.TestCase):
    def test_load_push_journal_invalid_payload(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            path = journal_path_for_wordlist(wordlist)
            path.write_text("{not json", encoding="utf-8")
            self.assertIsNone(load_push_journal(wordlist))

            path.write_text('{"schema_version": 99}', encoding="utf-8")
            self.assertIsNone(load_push_journal(wordlist))

            path.write_text(
                json.dumps({"schema_version": 2, "state": "done"}),
                encoding="utf-8",
            )
            self.assertIsNone(load_push_journal(wordlist))

    def test_recover_skips_missing_backup(self):
        with tempfile.TemporaryDirectory() as d:
            missing_wordlist = str(Path(d) / "missing-wordlist.txt")
            missing_dict = str(Path(d) / "missing-dict.txt")
            journal = PushJournal(
                schema_version=JOURNAL_SCHEMA_VERSION,
                transaction_id=str(__import__("uuid").uuid4()),
                command="push",
                pid=1,
                started="2026-01-01T00:00:00+00:00",
                state=JOURNAL_STATE_WRITING,
                wordlist=missing_wordlist,
                wordlist_hash_before=None,
                wordlist_hash_after=None,
                wordlist_backup_path=None,
                wordlist_existed_before=False,
                targets=[
                    JournalTarget(
                        name="d",
                        path=missing_dict,
                        hash_before=None,
                        hash_after=None,
                        backup_path=None,
                        existed_before=False,
                    ),
                ],
            )
            result = recover_from_journal(journal)
            self.assertIn("wordlist", result.skipped)
            self.assertIn("d", result.skipped)

    def test_journal_session_mark_and_discard(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            dict_path.write_text("alpha\n", encoding="utf-8")
            run = SyncRun(
                wordlist=str(wordlist),
                dictionaries=[Dictionary("d", str(dict_path), DictionaryFormat.TEXT)],
            )
            tx = PushTransaction.begin(wordlist, run.dictionaries, dry_run=False)
            session = PushJournalSession.begin(
                wordlist,
                command="push",
                tx=tx,
                dictionaries=run.dictionaries,
            )
            self.assertTrue(journal_path_for_wordlist(wordlist).is_file())
            session.mark_wordlist_write_started(file_content_hash(wordlist))
            session.mark_wordlist_write_completed()
            session.mark_write_started("d", file_content_hash(dict_path))
            session.mark_target_written("d")
            session.discard()
            self.assertFalse(journal_path_for_wordlist(wordlist).exists())
            tx.close()

    def test_unfinished_journal_exit_skips_recover(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            _write_journal(wordlist)
            self.assertIsNone(
                unfinished_journal_exit(CliOptions(wordlist=str(wordlist)), "recover"),
            )

    def test_doctor_reports_unfinished_journal(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            _write_journal(wordlist)
            run = SyncRun(wordlist=str(wordlist), dictionaries=[])
            report = doctor_mod.build_doctor_report(run)
            self.assertTrue(report.has_errors)
            self.assertTrue(
                any("unfinished push journal" in check.message for check in report.checks),
            )
            self.assertTrue(any(action.id == "recover-push" for action in report.actions))

    def test_mutating_command_scope_journal_then_lock(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            with mutating_command_scope(CliOptions(wordlist=str(wordlist)), "status") as scope:
                exit_code = scope if isinstance(scope, int) else None
                self.assertIsNone(exit_code)

    def test_discard_journal_no_file(self):
        with tempfile.TemporaryDirectory() as d:
            discard_journal(Path(d) / "wordlist.txt")

    def test_file_content_hash_oserror(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wordlist.txt"
            path.write_text("alpha\n", encoding="utf-8")
            with patch("builtins.open", side_effect=OSError("nope")):
                self.assertIsNone(file_content_hash(path))

    def test_load_push_journal_bad_targets(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            path = journal_path_for_wordlist(wordlist)
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "state": "writing",
                        "transaction_id": "tx",
                        "command": "push",
                        "pid": 1,
                        "started": "2026-01-01T00:00:00+00:00",
                        "wordlist": str(wordlist),
                        "targets": [{"name": "d"}],
                    }
                ),
                encoding="utf-8",
            )
            self.assertIsNone(load_push_journal(wordlist))

    def test_recover_restore_failure(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            bak = wordlist.with_suffix(wordlist.suffix + ".bak")
            wordlist.write_text("new\n", encoding="utf-8")
            bak.write_text("old\n", encoding="utf-8")
            journal = PushJournal(
                schema_version=JOURNAL_SCHEMA_VERSION,
                transaction_id=str(__import__("uuid").uuid4()),
                command="push",
                pid=1,
                started="2026-01-01T00:00:00+00:00",
                state=JOURNAL_STATE_WRITING,
                wordlist=str(wordlist),
                wordlist_hash_before=None,
                wordlist_hash_after=file_content_hash(wordlist),
                wordlist_backup_path=str(bak),
                wordlist_write_started=True,
                wordlist_write_completed=True,
                targets=[],
            )
            with patch("shutil.copy2", side_effect=OSError("nope")):
                result = recover_from_journal(journal)
            self.assertIn("wordlist", result.failed)

    def test_recover_skips_missing_backup_file(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("new\n", encoding="utf-8")
            journal = PushJournal(
                schema_version=JOURNAL_SCHEMA_VERSION,
                transaction_id=str(__import__("uuid").uuid4()),
                command="push",
                pid=1,
                started="2026-01-01T00:00:00+00:00",
                state=JOURNAL_STATE_WRITING,
                wordlist=str(wordlist),
                wordlist_hash_before=None,
                wordlist_hash_after=file_content_hash(wordlist),
                wordlist_backup_path=str(wordlist.with_suffix(wordlist.suffix + ".bak")),
                wordlist_write_started=True,
                wordlist_write_completed=True,
                targets=[],
            )
            result = recover_from_journal(journal)
            self.assertIn("wordlist", result.failed)

    def test_session_discard_oserror(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            dict_path.write_text("alpha\n", encoding="utf-8")
            run = SyncRun(
                wordlist=str(wordlist),
                dictionaries=[Dictionary("d", str(dict_path), DictionaryFormat.TEXT)],
            )
            tx = PushTransaction.begin(wordlist, run.dictionaries, dry_run=False)
            session = PushJournalSession.begin(
                wordlist,
                command="push",
                tx=tx,
                dictionaries=run.dictionaries,
            )
            with patch.object(Path, "unlink", side_effect=OSError("nope")):
                session.discard()
            tx.close()

    def test_discard_journal_oserror(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            _write_journal(wordlist)
            with patch.object(Path, "unlink", side_effect=OSError("nope")):
                discard_journal(wordlist)

    def test_journal_property(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            dict_path.write_text("alpha\n", encoding="utf-8")
            run = SyncRun(
                wordlist=str(wordlist),
                dictionaries=[Dictionary("d", str(dict_path), DictionaryFormat.TEXT)],
            )
            tx = PushTransaction.begin(wordlist, run.dictionaries, dry_run=False)
            session = PushJournalSession.begin(
                wordlist,
                command="push",
                tx=tx,
                dictionaries=run.dictionaries,
            )
            self.assertEqual(session.journal.command, "push")
            session.discard()
            tx.close()


class TestRecoverCommandCoverage(unittest.TestCase):
    def test_recover_lock_exit(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            with _locked_patch(wordlist):
                code = recover_mod.cmd_recover(CliOptions(wordlist=str(wordlist)))
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))

    def test_recover_no_journal_json(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = recover_mod.cmd_recover(
                    CliOptions(wordlist=str(wordlist), json_output=True),
                )
            payload = json.loads(buf.getvalue())
            self.assertEqual(code, int(ExitCode.OK))
            self.assertEqual(payload["action"], "none")

    def test_recover_text_failed(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            _write_journal(wordlist)
            with patch(
                "spell_sync.recover_cmd.recover_from_journal",
                return_value=RecoverResult((), (), ("wordlist",)),
            ):
                code = recover_mod.cmd_recover(CliOptions(wordlist=str(wordlist), yes=True))
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))

    def test_recover_text_dry_run_would_restore(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            _write_journal(wordlist)
            with patch(
                "spell_sync.recover_cmd.recover_from_journal",
                return_value=RecoverResult(("wordlist",), (), ()),
            ):
                code = recover_mod.cmd_recover(
                    CliOptions(wordlist=str(wordlist), dry_run=True),
                )
            self.assertEqual(code, int(ExitCode.OK))

    def test_recover_text_dry_run_empty(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            _write_journal(wordlist)
            with patch(
                "spell_sync.recover_cmd.recover_from_journal",
                return_value=RecoverResult((), ("wordlist",), ()),
            ):
                code = recover_mod.cmd_recover(
                    CliOptions(wordlist=str(wordlist), dry_run=True),
                )
            self.assertEqual(code, int(ExitCode.OK))

    def test_recover_text_success(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            _write_journal(wordlist)
            with patch(
                "spell_sync.recover_cmd.recover_from_journal",
                return_value=RecoverResult(("wordlist",), (), ()),
            ):
                code = recover_mod.cmd_recover(CliOptions(wordlist=str(wordlist), yes=True))
            self.assertEqual(code, int(ExitCode.OK))

    def test_recover_interactive_confirmed(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            _write_journal(wordlist)
            with (
                patch("sys.stdin.isatty", return_value=True),
                patch("builtins.input", return_value="y"),
                patch(
                    "spell_sync.recover_cmd.recover_from_journal",
                    return_value=RecoverResult((), (), ()),
                ),
            ):
                code = recover_mod.cmd_recover(CliOptions(wordlist=str(wordlist)))
            self.assertEqual(code, int(ExitCode.OK))

    def test_recover_interactive_cancelled(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            _write_journal(wordlist)
            with (
                patch("sys.stdin.isatty", return_value=True),
                patch("builtins.input", return_value="n"),
            ):
                code = recover_mod.cmd_recover(CliOptions(wordlist=str(wordlist)))
            self.assertEqual(code, int(ExitCode.CANCELLED))

    def test_recover_interactive_eof(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            _write_journal(wordlist)
            with (
                patch("sys.stdin.isatty", return_value=True),
                patch("builtins.input", side_effect=EOFError),
            ):
                code = recover_mod.cmd_recover(CliOptions(wordlist=str(wordlist)))
            self.assertEqual(code, int(ExitCode.CANCELLED))
