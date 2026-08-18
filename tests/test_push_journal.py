"""Push journal and recover command tests."""

import io
import json
import os
import tempfile
import unittest
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from service_test_utils import (
    patch_recover_service,
    recoverable_preview,
    recovery_execution,
)

import spell_sync.commands as commands
import spell_sync.doctor as doctor_mod
import spell_sync.recover_cmd as recover_mod
from spell_sync.cli_options import CliOptions
from spell_sync.command_helpers import mutating_command_scope
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import write_text_words
from spell_sync.operation_lock import OperationLocked, OperationLockInfo, lock_path_for_wordlist
from spell_sync.push_journal import (
    JOURNAL_SCHEMA_VERSION,
    JOURNAL_STATE_COMPLETED,
    JOURNAL_STATE_WRITING,
    JournalTarget,
    PushJournal,
    PushJournalSession,
    RecoverResult,
    cleanup_after_successful_recovery,
    discard_completed_journal,
    file_content_hash,
    journal_path_for_wordlist,
    journal_payload,
    load_journal_result,
    recover_from_journal,
    safe_discard_journal_file,
    safe_discard_txn_snapshots,
)
from spell_sync.push_transaction import PushTransaction, txn_snapshot_root
from spell_sync.sync_run import PushResult
from tests.journal_test_utils import write_restore_scenario_journal, write_test_journal
from tests.runtime_helpers import make_sync_run


def _locked_patch(wordlist: Path):
    info = OperationLockInfo(99, "2026-01-01T00:00:00+00:00", "push", str(wordlist))
    lock_path = lock_path_for_wordlist(wordlist)
    return patch(
        "spell_sync.mutation_guards.acquire_operation_lock",
        side_effect=OperationLocked(info, lock_path),
    )


def _write_journal(wordlist: Path, *, command: str = "push") -> None:
    write_test_journal(
        wordlist,
        command=command,
        wordlist_write_started=True,
        wordlist_write_completed=True,
    )


def _disable_all_targets(wordlist: Path) -> None:
    (wordlist.parent / "spell-sync.toml").write_text(
        "[dictionaries]\n"
        "editors = false\n"
        "chrome = false\n"
        "edge = false\n"
        "brave = false\n"
        "vivaldi = false\n"
        "firefox = false\n"
        "neovim = false\n"
        "sublime = false\n"
        "jetbrains = false\n"
        "hunspell = false\n"
        "obsidian = false\n"
        "libreoffice = false\n",
        encoding="utf-8",
    )


class TestPushJournalLifecycle(unittest.TestCase):
    def test_successful_push_removes_journal(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "dict.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(dict_path, ["alpha"], "utf-8", False, quiet=True)
            run = make_sync_run(
                wordlist,
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
            run = make_sync_run(
                str(wordlist),
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
            run = make_sync_run(
                wordlist,
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
            _disable_all_targets(wordlist)
            _write_journal(wordlist)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = commands.cmd_pull(
                    CliOptions(wordlist=str(wordlist), json_output=True),
                )
            payload = json.loads(buf.getvalue())
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))
            self.assertEqual(payload["reason"], "unfinished_transaction")
            self.assertIn("journal", payload)
            self.assertEqual(payload["command"], "pull")

    def test_recover_allowed_with_unfinished_journal(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            _write_journal(wordlist)
            preview = recoverable_preview(str(wordlist))
            execution = recovery_execution(RecoverResult((), (), ()), preview=preview)
            with patch_recover_service(
                inspect_recovery=preview,
                execute_recovery=execution,
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
            preview = recoverable_preview(str(wordlist))
            buf = io.StringIO()
            with (
                patch_recover_service(inspect_recovery=preview),
                redirect_stdout(buf),
            ):
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
    def test_load_journal_result_invalid_payload(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            path = journal_path_for_wordlist(wordlist)
            path.write_text("{not json", encoding="utf-8")
            self.assertIsNone(load_journal_result(wordlist).journal)

            path.write_text('{"schema_version": 99}', encoding="utf-8")
            self.assertIsNone(load_journal_result(wordlist).journal)

            path.write_text(
                json.dumps({"schema_version": 2, "state": "done"}),
                encoding="utf-8",
            )
            self.assertIsNone(load_journal_result(wordlist).journal)

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
            run = make_sync_run(
                str(wordlist),
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

    def test_doctor_reports_unfinished_journal(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            _write_journal(wordlist)
            run = make_sync_run(str(wordlist), dictionaries=[])
            report = doctor_mod.build_doctor_report(run)
            self.assertTrue(report.has_errors)
            self.assertTrue(
                any("interrupted update" in check.message for check in report.checks),
            )
            self.assertTrue(any(action.id == "recover-push" for action in report.actions))

    def test_doctor_reports_completed_journal_cleanup(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            write_test_journal(wordlist, state=JOURNAL_STATE_COMPLETED)
            run = make_sync_run(str(wordlist), dictionaries=[])
            report = doctor_mod.build_doctor_report(run)
            self.assertFalse(report.has_errors)
            self.assertTrue(
                any("recovery files remain" in check.message for check in report.checks),
                [check.message for check in report.checks],
            )
            self.assertTrue(any(action.id == "recover-cleanup" for action in report.actions))

    def test_doctor_reports_corrupt_and_unsupported_journal(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal = journal_path_for_wordlist(wordlist)
            journal.write_text("{not-json", encoding="utf-8")
            run = make_sync_run(str(wordlist), dictionaries=[])
            report = doctor_mod.build_doctor_report(run)
            self.assertTrue(report.has_errors)
            self.assertTrue(
                any(
                    "damaged interrupted-update record" in check.message for check in report.checks
                ),
            )

    def test_mutating_command_scope_journal_then_lock(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            with mutating_command_scope(CliOptions(wordlist=str(wordlist)), "status") as scope:
                exit_code = scope if isinstance(scope, int) else None
                self.assertIsNone(exit_code)

    def test_discard_journal_no_file(self):
        with tempfile.TemporaryDirectory() as d:
            ok, _detail = safe_discard_journal_file(Path(d) / "wordlist.txt")
            self.assertTrue(ok)

    def test_file_content_hash_oserror(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wordlist.txt"
            path.write_text("alpha\n", encoding="utf-8")
            with patch("builtins.open", side_effect=OSError("nope")):
                self.assertIsNone(file_content_hash(path))

    def test_load_journal_result_bad_targets(self):
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
            self.assertIsNone(load_journal_result(wordlist).journal)

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
            run = make_sync_run(
                str(wordlist),
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

    def test_load_journal_result_oserror(self):
        from spell_sync.push_journal import JournalLoadStatus, load_journal_result

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            _write_journal(wordlist)
            with patch(
                "spell_sync.push_journal.read_trusted_regular_file",
                side_effect=OSError(13, "Permission denied", str(wordlist.parent)),
            ):
                result = load_journal_result(wordlist)
            self.assertEqual(result.status, JournalLoadStatus.CORRUPT)
            self.assertEqual(result.detail, "unreadable")
            self.assertNotIn(str(wordlist.parent), result.detail or "")

    def test_session_discard_swallows_remove_errors(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            dict_path.write_text("alpha\n", encoding="utf-8")
            run = make_sync_run(
                str(wordlist),
                dictionaries=[Dictionary("d", str(dict_path), DictionaryFormat.TEXT)],
            )
            tx = PushTransaction.begin(wordlist, run.dictionaries, dry_run=False)
            session = PushJournalSession.begin(
                wordlist,
                command="push",
                tx=tx,
                dictionaries=run.dictionaries,
            )
            with patch(
                "spell_sync.push_journal.remove_trusted_file",
                side_effect=OSError("remove failed"),
            ):
                session.discard()
            tx.close()

    def test_discard_journal_oserror(self):
        from spell_sync.secure_artifacts import SecureArtifactError

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            _write_journal(wordlist)
            with patch(
                "spell_sync.push_journal.remove_trusted_file",
                side_effect=SecureArtifactError("unlink_failed", "nope"),
            ):
                ok, detail = safe_discard_journal_file(wordlist)
            self.assertFalse(ok)
            self.assertIsNotNone(detail)

    def test_journal_property(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            dict_path.write_text("alpha\n", encoding="utf-8")
            run = make_sync_run(
                str(wordlist),
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

    def test_cleanup_after_successful_recovery_snapshot_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal = write_test_journal(
                wordlist,
                state=JOURNAL_STATE_COMPLETED,
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            with patch(
                "spell_sync.push_journal.safe_discard_txn_snapshots",
                return_value=(False, "bad snap"),
            ):
                result = cleanup_after_successful_recovery(journal)
            self.assertFalse(result.ok)
            # Journal is discarded first so a stuck journal cannot point at
            # already-deleted snapshots.
            self.assertTrue(result.journal_removed)
            self.assertFalse(result.snapshots_removed)

    def test_discard_completed_journal_journal_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            write_test_journal(
                wordlist,
                state=JOURNAL_STATE_COMPLETED,
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            with patch(
                "spell_sync.push_journal.safe_discard_txn_snapshots",
                return_value=(True, None),
            ):
                with patch(
                    "spell_sync.push_journal.safe_discard_journal_file",
                    return_value=(False, "journal stuck"),
                ):
                    result = discard_completed_journal(wordlist)
            self.assertFalse(result.ok)
            self.assertFalse(result.snapshots_removed)
            self.assertFalse(result.journal_removed)

    def test_safe_discard_txn_snapshots_bad_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            ok, detail = safe_discard_txn_snapshots(
                wordlist,
                "00000000-0000-4000-8000-000000000001",
                str(Path(tmp) / "outside"),
            )
            self.assertFalse(ok)
            self.assertIsNotNone(detail)

    def test_cleanup_after_successful_recovery_journal_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal = write_test_journal(
                wordlist,
                state=JOURNAL_STATE_COMPLETED,
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            with patch(
                "spell_sync.push_journal.safe_discard_txn_snapshots",
                return_value=(True, None),
            ):
                with patch(
                    "spell_sync.push_journal.safe_discard_journal_file",
                    return_value=(False, "journal stuck"),
                ):
                    result = cleanup_after_successful_recovery(journal)
            self.assertFalse(result.ok)
            self.assertFalse(result.snapshots_removed)
            self.assertFalse(result.journal_removed)

    def test_safe_discard_snapshot_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal = write_test_journal(
                wordlist,
                state=JOURNAL_STATE_COMPLETED,
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            snap = Path(journal.snapshot_dir)
            outside = Path(tmp) / "outside"
            outside.mkdir()
            if snap.exists():
                for child in snap.iterdir():
                    child.unlink()
                snap.rmdir()
            snap.symlink_to(outside, target_is_directory=True)
            ok, detail = safe_discard_txn_snapshots(
                wordlist,
                journal.transaction_id,
                journal.snapshot_dir,
            )
            self.assertFalse(ok)
            self.assertIn("symlink", detail or "")

    def test_safe_discard_snapshot_rmtree_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal = write_test_journal(
                wordlist,
                state=JOURNAL_STATE_COMPLETED,
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            with patch(
                "spell_sync.push_journal.remove_trusted_tree",
                side_effect=OSError(16, "Device or resource busy", journal.snapshot_dir),
            ):
                ok, detail = safe_discard_txn_snapshots(
                    wordlist,
                    journal.transaction_id,
                    journal.snapshot_dir,
                )
            self.assertFalse(ok)
            self.assertEqual(detail, "snapshot cleanup failed")
            self.assertNotIn(journal.snapshot_dir, detail or "")

    def test_safe_discard_journal_outside_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "project" / "wordlist.txt"
            wordlist.parent.mkdir()
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal = wordlist.parent / ".spell-sync.journal.json"
            journal.write_text("{}", encoding="utf-8")
            journal.unlink()
            journal.symlink_to(Path(tmp) / "outside")
            (Path(tmp) / "outside").write_text("{}", encoding="utf-8")
            ok, _detail = safe_discard_journal_file(wordlist)
            self.assertFalse(ok)

    def test_discard_completed_journal_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            result = discard_completed_journal(wordlist)
            self.assertFalse(result.ok)

    def test_safe_discard_snapshot_resolve_oserror(self):
        from spell_sync.push_journal import DiscardSafetyError, _safe_txn_snapshot_dir

        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal = write_test_journal(
                wordlist,
                state=JOURNAL_STATE_COMPLETED,
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            snapshot_dir = journal.snapshot_dir
            transaction_id = journal.transaction_id
            snap = Path(snapshot_dir)
            with patch("spell_sync.push_journal.txn_snapshot_root", return_value=snap):
                with patch.object(Path, "resolve", side_effect=OSError("broken")):
                    with self.assertRaises(DiscardSafetyError):
                        _safe_txn_snapshot_dir(wordlist, transaction_id, snapshot_dir)

    def test_safe_discard_snapshot_not_directory(self):
        from spell_sync.push_journal import DiscardSafetyError, _safe_txn_snapshot_dir

        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal = write_test_journal(
                wordlist,
                state=JOURNAL_STATE_COMPLETED,
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            snap = Path(journal.snapshot_dir)
            resolved = snap.resolve()
            with patch.object(type(snap), "is_symlink", return_value=False):
                with patch.object(type(snap), "resolve", return_value=resolved):
                    with patch.object(type(snap), "is_dir", return_value=False):
                        with self.assertRaises(DiscardSafetyError):
                            _safe_txn_snapshot_dir(
                                wordlist,
                                journal.transaction_id,
                                journal.snapshot_dir,
                            )

    def test_safe_discard_journal_uses_descriptor_not_resolve_spoof(self):
        from spell_sync.push_journal import journal_path_for_wordlist

        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "project" / "wordlist.txt"
            wordlist.parent.mkdir(parents=True)
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal = journal_path_for_wordlist(wordlist)
            journal.write_text("{}", encoding="utf-8")
            outside = (Path(tmp) / "outside").resolve()
            real_resolve = Path.resolve

            def selective_resolve(self: Path) -> Path:
                if self == journal:
                    return outside
                return real_resolve(self)

            with patch.object(Path, "resolve", selective_resolve):
                ok, detail = safe_discard_journal_file(wordlist)
            self.assertTrue(ok)
            self.assertIsNone(detail)
            self.assertFalse(journal.exists())

    def test_safe_discard_snapshot_missing_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            journal = write_test_journal(
                wordlist,
                state=JOURNAL_STATE_COMPLETED,
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            snap = Path(journal.snapshot_dir)
            snap_file = snap.with_suffix(".snap-file")
            if snap.is_dir():
                for child in snap.iterdir():
                    child.unlink()
                snap.rmdir()
            snap_file.write_text("x", encoding="utf-8")
            ok, _detail = safe_discard_txn_snapshots(
                wordlist,
                journal.transaction_id,
                str(snap_file),
            )
            self.assertFalse(ok)


class TestRecoverCommandCoverage(unittest.TestCase):
    def test_recover_lock_exit(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            preview = recoverable_preview(str(wordlist))
            execution = recovery_execution(ExitCode.PUSH_ABORT, preview=preview)
            with (
                _locked_patch(wordlist),
                patch_recover_service(
                    inspect_recovery=preview,
                    execute_recovery=execution,
                ),
            ):
                code = recover_mod.cmd_recover(CliOptions(wordlist=str(wordlist), yes=True))
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
            preview = recoverable_preview(str(wordlist))
            execution = recovery_execution(
                RecoverResult((), (), ("wordlist",)),
                preview=preview,
            )
            with patch_recover_service(
                inspect_recovery=preview,
                execute_recovery=execution,
            ):
                code = recover_mod.cmd_recover(CliOptions(wordlist=str(wordlist), yes=True))
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))

    def test_recover_text_dry_run_would_restore(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            _write_journal(wordlist)
            preview = recoverable_preview(str(wordlist))
            execution = recovery_execution(
                RecoverResult(("wordlist",), (), ()),
                preview=preview,
            )
            with patch_recover_service(
                inspect_recovery=preview,
                execute_recovery=execution,
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
            preview = recoverable_preview(str(wordlist))
            execution = recovery_execution(
                RecoverResult((), ("wordlist",), ()),
                preview=preview,
            )
            with patch_recover_service(
                inspect_recovery=preview,
                execute_recovery=execution,
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
            preview = recoverable_preview(str(wordlist))
            execution = recovery_execution(
                RecoverResult(("wordlist",), (), ()),
                preview=preview,
            )
            with patch_recover_service(
                inspect_recovery=preview,
                execute_recovery=execution,
            ):
                code = recover_mod.cmd_recover(CliOptions(wordlist=str(wordlist), yes=True))
            self.assertEqual(code, int(ExitCode.OK))

    def test_recover_interactive_confirmed(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            _write_journal(wordlist)
            preview = recoverable_preview(str(wordlist))
            execution = recovery_execution(RecoverResult((), (), ()), preview=preview)
            with (
                patch("sys.stdin.isatty", return_value=True),
                patch("builtins.input", return_value="y"),
                patch_recover_service(
                    inspect_recovery=preview,
                    execute_recovery=execution,
                ),
            ):
                code = recover_mod.cmd_recover(CliOptions(wordlist=str(wordlist)))
            self.assertEqual(code, int(ExitCode.OK))

    def test_recover_interactive_cancelled(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            _write_journal(wordlist)
            preview = recoverable_preview(str(wordlist))
            with (
                patch("sys.stdin.isatty", return_value=True),
                patch("builtins.input", return_value="n"),
                patch_recover_service(inspect_recovery=preview),
            ):
                code = recover_mod.cmd_recover(CliOptions(wordlist=str(wordlist)))
            self.assertEqual(code, int(ExitCode.CANCELLED))

    def test_recover_interactive_eof(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            _write_journal(wordlist)
            preview = recoverable_preview(str(wordlist))
            with (
                patch("sys.stdin.isatty", return_value=True),
                patch("builtins.input", side_effect=EOFError),
                patch_recover_service(inspect_recovery=preview),
            ):
                code = recover_mod.cmd_recover(CliOptions(wordlist=str(wordlist)))
            self.assertEqual(code, int(ExitCode.CANCELLED))


class TestPushJournalSchemaBranchCoverage(unittest.TestCase):
    def test_load_rejects_non_int_schema(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            path = journal_path_for_wordlist(wordlist)
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "2",
                        "transaction_id": str(uuid.uuid4()),
                        "command": "push",
                        "pid": 1,
                        "started": "t",
                        "state": "writing",
                        "wordlist": str(wordlist),
                        "targets": [],
                    }
                ),
                encoding="utf-8",
            )
            from spell_sync.push_journal import JournalLoadStatus

            self.assertEqual(
                load_journal_result(wordlist).status,
                JournalLoadStatus.UNSUPPORTED_SCHEMA,
            )

    def test_secure_file_mode_oserror(self):
        from spell_sync.push_journal import _secure_file_mode

        with patch("spell_sync.push_journal.os.chmod", side_effect=OSError("nope")):
            self.assertIsNone(_secure_file_mode(Path("/tmp/x"), 0o600))


class TestPushJournalLoadCoverage(unittest.TestCase):
    def _write_raw(self, wordlist: Path, payload: dict) -> None:
        journal_path_for_wordlist(wordlist).write_text(json.dumps(payload), encoding="utf-8")

    def test_parse_rejects_bad_schema_command_and_targets(self):
        from spell_sync.push_journal import JournalLoadStatus

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            tid = str(uuid.uuid4())
            base = {
                "transaction_id": tid,
                "command": "push",
                "pid": 1,
                "started": "t",
                "state": "writing",
                "wordlist": str(wordlist),
                "targets": [],
            }
            self._write_raw(wordlist, {**base, "schema_version": True})
            self.assertEqual(
                load_journal_result(wordlist).status,
                JournalLoadStatus.UNSUPPORTED_SCHEMA,
            )
            self._write_raw(wordlist, {**base, "schema_version": 2, "command": "nope"})
            self.assertEqual(load_journal_result(wordlist).status, JournalLoadStatus.CORRUPT)
            self._write_raw(wordlist, {**base, "schema_version": 2, "targets": "bad"})
            self.assertEqual(load_journal_result(wordlist).status, JournalLoadStatus.CORRUPT)
            self._write_raw(wordlist, {**base, "schema_version": 2, "targets": ["bad"]})
            self.assertEqual(load_journal_result(wordlist).status, JournalLoadStatus.CORRUPT)
            self._write_raw(
                wordlist,
                {**base, "schema_version": 2, "snapshot_dir": 1},
            )
            self.assertEqual(load_journal_result(wordlist).status, JournalLoadStatus.CORRUPT)

    def test_snapshot_hash_mismatch_corrupt(self):
        from spell_sync.push_journal import JournalLoadStatus

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "dict.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            dict_path.write_text("a\n", encoding="utf-8")
            tid = str(uuid.uuid4())
            snap = txn_snapshot_root(wordlist, tid)
            snap.mkdir(parents=True)
            backup = snap / "dict.snap"
            backup.write_text("wrong\n", encoding="utf-8")
            self._write_raw(
                wordlist,
                {
                    "schema_version": 2,
                    "transaction_id": tid,
                    "command": "push",
                    "pid": 1,
                    "started": "t",
                    "state": "writing",
                    "wordlist": str(wordlist),
                    "snapshot_dir": str(snap),
                    "wordlist_hash_before": "a" * 64,
                    "wordlist_backup_path": str(backup),
                    "wordlist_existed_before": True,
                    "targets": [
                        {
                            "name": "d",
                            "path": str(dict_path),
                            "hash_before": "b" * 64,
                            "hash_after": None,
                            "backup_path": str(backup),
                            "existed_before": True,
                            "write_started": True,
                            "write_completed": False,
                        }
                    ],
                },
            )
            self.assertEqual(load_journal_result(wordlist).status, JournalLoadStatus.CORRUPT)


class TestRecoverJournalEdgeCases(unittest.TestCase):
    def test_failed_snapshot_hash_and_missing_destination(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            target = Path(d) / "missing.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            bak = Path(d) / "snap.txt"
            bak.write_text("old\n", encoding="utf-8")
            wrong_hash = "0" * 64
            journal = PushJournal(
                schema_version=2,
                transaction_id=str(uuid.uuid4()),
                command="push",
                pid=1,
                started="t",
                state=JOURNAL_STATE_WRITING,
                wordlist=str(wordlist),
                wordlist_hash_before=wrong_hash,
                wordlist_hash_after="c" * 64,
                wordlist_backup_path=str(bak),
                wordlist_existed_before=True,
                wordlist_write_started=True,
                wordlist_write_completed=True,
                targets=[
                    JournalTarget(
                        name="gone",
                        path=str(target),
                        hash_before=wrong_hash,
                        hash_after="d" * 64,
                        backup_path=str(bak),
                        existed_before=True,
                        write_started=True,
                        write_completed=True,
                    )
                ],
            )
            result = recover_from_journal(journal)
            self.assertIn("gone", result.failed)
            self.assertIn("wordlist", result.failed)


class TestPushJournalRemainingBranches(unittest.TestCase):
    def test_parse_unsupported_schema_in_dict(self):
        from spell_sync.push_journal import JournalParseError, _parse_journal_dict

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            with self.assertRaises(JournalParseError):
                _parse_journal_dict(
                    {
                        "schema_version": 3,
                        "transaction_id": str(uuid.uuid4()),
                        "command": "push",
                        "pid": 1,
                        "started": "t",
                        "state": "writing",
                        "wordlist": str(wordlist),
                        "targets": [],
                    },
                    expected_wordlist=None,
                )

    def test_wordlist_snapshot_mismatch(self):
        from spell_sync.push_journal import JournalLoadStatus

        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            tid = str(uuid.uuid4())
            snap = txn_snapshot_root(wordlist, tid)
            snap.mkdir(parents=True)
            backup = snap / "wl.snap"
            backup.write_text("wrong\n", encoding="utf-8")
            journal_path_for_wordlist(wordlist).write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "transaction_id": tid,
                        "command": "push",
                        "pid": 1,
                        "started": "t",
                        "state": "writing",
                        "wordlist": str(wordlist),
                        "snapshot_dir": str(snap),
                        "wordlist_hash_before": "0" * 64,
                        "wordlist_backup_path": str(backup),
                        "wordlist_existed_before": True,
                        "wordlist_write_started": True,
                        "targets": [],
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(load_journal_result(wordlist).status, JournalLoadStatus.CORRUPT)

    def test_recover_missing_destination_restore(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "gone.txt"
            bak = Path(d) / "snap.txt"
            bak.write_text("old\n", encoding="utf-8")
            hb = file_content_hash(bak)
            journal = PushJournal(
                schema_version=2,
                transaction_id=str(uuid.uuid4()),
                command="push",
                pid=1,
                started="t",
                state=JOURNAL_STATE_WRITING,
                wordlist=str(Path(d) / "wl.txt"),
                wordlist_hash_before=None,
                wordlist_hash_after=None,
                wordlist_backup_path=None,
                wordlist_existed_before=True,
                targets=[
                    JournalTarget(
                        name="gone",
                        path=str(target),
                        hash_before=hb,
                        hash_after=None,
                        backup_path=str(bak),
                        existed_before=True,
                        write_started=True,
                        write_completed=True,
                    )
                ],
            )
            result = recover_from_journal(journal)
            self.assertIn("gone", result.restored)
            self.assertEqual(target.read_text(encoding="utf-8"), "old\n")

    def test_recover_existing_missing_file_with_hash_after(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "gone.txt"
            bak = Path(d) / "snap.txt"
            bak.write_text("old\n", encoding="utf-8")
            hb = file_content_hash(bak)
            ha = "f" * 64
            journal = PushJournal(
                schema_version=2,
                transaction_id=str(uuid.uuid4()),
                command="push",
                pid=1,
                started="t",
                state=JOURNAL_STATE_WRITING,
                wordlist=str(Path(d) / "wl.txt"),
                wordlist_hash_before=None,
                wordlist_hash_after=None,
                wordlist_backup_path=None,
                wordlist_existed_before=True,
                targets=[
                    JournalTarget(
                        name="gone",
                        path=str(target),
                        hash_before=hb,
                        hash_after=ha,
                        backup_path=str(bak),
                        existed_before=True,
                        write_started=True,
                        write_completed=True,
                    )
                ],
            )
            result = recover_from_journal(journal)
            self.assertIn("gone", result.restored)

    def test_discard_completed_with_snapshot_dir(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            journal = write_test_journal(wordlist, state="completed")
            snap = Path(journal.snapshot_dir or "")
            discard_completed_journal(wordlist)
            self.assertFalse(journal_path_for_wordlist(wordlist).exists())
            if journal.snapshot_dir:
                self.assertFalse(snap.exists())
