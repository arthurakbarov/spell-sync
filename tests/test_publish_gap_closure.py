"""Close remaining publish-CI strict/presentation line gaps."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

from spell_sync.application.reports import RecoveryExecution, RecoveryOutcome, RecoveryStatus
from spell_sync.cli_options import CliOptions
from spell_sync.exit_codes import ExitCode
from spell_sync.mutation_guards import unfinished_journal_exit_from_result_for
from spell_sync.push_journal import JournalLoadResult, JournalLoadStatus
from tests.tui.fake_service import sample_recovery_preview


class TestPublishGapClosure(unittest.TestCase):
    def test_tui_lazy_run_ui_export(self) -> None:
        import spell_sync.tui as tui_mod

        self.assertTrue(callable(tui_mod.run_ui))
        with self.assertRaises(AttributeError):
            getattr(tui_mod, "not_a_real_export")

    def test_mutation_guards_unsafe_artifact_human_message(self) -> None:
        with patch("spell_sync.mutation_guards.log.abort") as abort:
            with patch(
                "spell_sync.mutation_guards.wordlist_path",
                return_value=Path("/tmp/wordlist.txt"),
            ):
                code = unfinished_journal_exit_from_result_for(
                    "push",
                    JournalLoadResult(
                        JournalLoadStatus.UNSAFE_ARTIFACT,
                        None,
                        detail="symlink",
                    ),
                    json_output=False,
                )
        self.assertEqual(code, int(ExitCode.PUSH_ABORT))
        abort.assert_called_once()
        self.assertIn("unsafe", abort.call_args[0][0].lower())

    def test_recover_cmd_cleanup_discard_and_failed_exit(self) -> None:
        from service_test_utils import patch_recover_service

        import spell_sync.recover_cmd as recover_mod

        with patch_recover_service(
            inspect_recovery=sample_recovery_preview(
                status=RecoveryStatus.COMPLETED_CLEANUP_PENDING,
                can_cleanup=True,
                can_recover=False,
            )
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = recover_mod.cmd_recover(
                    CliOptions(wordlist="/tmp/w.txt", dry_run=True, json_output=True)
                )
            self.assertEqual(code, int(ExitCode.OK))
            self.assertEqual(json.loads(buf.getvalue())["action"], "cleanup")

        failed_cleanup = RecoveryExecution(
            preview=sample_recovery_preview(
                status=RecoveryStatus.COMPLETED_CLEANUP_PENDING,
                can_cleanup=True,
            ),
            result=ExitCode.PUSH_ABORT,
            outcome=RecoveryOutcome.FAILED,
            message="cleanup failed",
        )
        with patch_recover_service(
            inspect_recovery=sample_recovery_preview(
                status=RecoveryStatus.COMPLETED_CLEANUP_PENDING,
                can_cleanup=True,
            ),
            execute_recovery_cleanup=failed_cleanup,
        ):
            with patch("spell_sync.recover_cmd.log.abort") as abort:
                code = recover_mod.cmd_recover(CliOptions(wordlist="/tmp/w.txt", yes=True))
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))
            abort.assert_called_once()

        failed_discard = RecoveryExecution(
            preview=sample_recovery_preview(
                status=RecoveryStatus.CORRUPT_JOURNAL,
                can_discard=True,
                can_recover=False,
            ),
            result=ExitCode.PUSH_ABORT,
            outcome=RecoveryOutcome.FAILED,
            message="discard failed",
        )
        with patch_recover_service(
            inspect_recovery=sample_recovery_preview(
                status=RecoveryStatus.CORRUPT_JOURNAL,
                can_discard=True,
                can_recover=False,
            ),
            execute_recovery_discard=failed_discard,
        ):
            with patch("spell_sync.recover_cmd.log.abort") as abort:
                code = recover_mod.cmd_recover(
                    CliOptions(
                        wordlist="/tmp/w.txt",
                        yes=True,
                        discard_corrupt_journal=True,
                    )
                )
            self.assertEqual(code, int(ExitCode.PUSH_ABORT))
            abort.assert_called_once()

        self.assertEqual(
            recover_mod._exit_from_recovery_execution(
                RecoveryExecution(
                    preview=sample_recovery_preview(),
                    result=0,
                    outcome=RecoveryOutcome.FAILED,
                    message="x",
                )
            ),
            int(ExitCode.PUSH_ABORT),
        )

    def test_setup_blocks_when_journal_appears_under_lock(self) -> None:
        from spell_sync.project_setup.execute import ProjectSetupOutcome, execute_project_setup

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            prepared = MagicMock()
            prepared.setup_id = "setup-1"
            prepared.wordlist_path = wordlist
            prepared.directories_to_create = ()
            prepared.files = ()
            prepared.enabled_target_ids = frozenset()

            with patch(
                "spell_sync.push_journal.load_journal_result",
                return_value=JournalLoadResult(
                    JournalLoadStatus.VALID_IN_PROGRESS,
                    MagicMock(),
                ),
            ):
                early = execute_project_setup(
                    prepared,
                    confirmed_setup_id="setup-1",
                    event_sink=None,
                )
            self.assertEqual(early.outcome, ProjectSetupOutcome.STOPPED_SAFELY)

            calls = {"n": 0}

            def _load(_path: Path) -> JournalLoadResult:
                calls["n"] += 1
                if calls["n"] == 1:
                    return JournalLoadResult(JournalLoadStatus.ABSENT, None)
                return JournalLoadResult(JournalLoadStatus.VALID_IN_PROGRESS, MagicMock())

            with (
                patch(
                    "spell_sync.project_setup.execute.acquire_operation_lock",
                    return_value=MagicMock(
                        __enter__=MagicMock(return_value=None),
                        __exit__=MagicMock(return_value=False),
                    ),
                ),
                patch(
                    "spell_sync.push_journal.load_journal_result",
                    side_effect=_load,
                ),
            ):
                locked = execute_project_setup(
                    prepared,
                    confirmed_setup_id="setup-1",
                    event_sink=None,
                )
            self.assertEqual(locked.outcome, ProjectSetupOutcome.STOPPED_SAFELY)
            self.assertIn("recovery", locked.message.lower())

    def test_push_journal_nested_unlink_oserror(self) -> None:
        from spell_sync.push_journal import recover_from_journal
        from tests.journal_test_utils import write_restore_scenario_journal

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            dictionary = root / "dict.txt"
            journal = write_restore_scenario_journal(wordlist, dictionary)
            real_mkstemp = __import__("tempfile").mkstemp

            def _mkstemp(*args, **kwargs):
                fd, name = real_mkstemp(*args, **kwargs)
                return fd, name

            with (
                patch("spell_sync.push_journal.tempfile.mkstemp", side_effect=_mkstemp),
                patch("spell_sync.push_journal.shutil.copy2"),
                patch("spell_sync.push_journal.os.replace", side_effect=OSError("replace boom")),
                patch.object(Path, "unlink", side_effect=OSError("unlink boom")),
            ):
                result = recover_from_journal(journal)
            self.assertTrue(result.failed)

    def test_push_abort_oserror_swallow_branches(self) -> None:
        from spell_sync.push_abort import (
            PushAbort,
            _best_effort_cleanup_after_complete_rollback,
            handle_failed_push_rollback,
        )
        from spell_sync.push_transaction import RollbackResult

        tx = MagicMock()
        tx.transaction_id = "tx-1"
        tx.discard_snapshots = MagicMock()
        tx.rollback.return_value = RollbackResult(
            restored=(),
            failed=("chrome",),
            conflicts=(),
        )
        journal_session = MagicMock()
        journal_session.mark_rollback_incomplete.side_effect = OSError("mark fail")
        journal_session.discard.side_effect = OSError("discard fail")
        abort = handle_failed_push_rollback(
            tx,
            journal_session,
            reason="write_failed",
            message="boom",
            journal_update_failed=False,
        )
        self.assertIsInstance(abort, PushAbort)
        self.assertTrue(abort.rollback_incomplete)
        _best_effort_cleanup_after_complete_rollback(tx, journal_session)
        tx.discard_snapshots.assert_called()

        # Cover journal_session is None branches on incomplete rollback + cleanup.
        abort_none = handle_failed_push_rollback(
            tx,
            None,
            reason="write_failed",
            message="boom",
            journal_update_failed=False,
        )
        self.assertTrue(abort_none.rollback_incomplete)
        _best_effort_cleanup_after_complete_rollback(tx, None)
