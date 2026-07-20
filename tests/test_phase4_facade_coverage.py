"""Unit coverage for Phase 4 pull/push facade paths."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from spell_sync.application.builders import (
    build_pull_preview,
    build_push_operation_report,
    build_target_updates_from_preview,
)
from spell_sync.application.reports import (
    OperationOutcome,
    PullExecution,
    PullPreview,
    PushExecution,
    PushPreview,
    TargetPreview,
)
from spell_sync.application.requests import (
    ProjectRef,
    PullRequest,
    PushRequest,
)
from spell_sync.application.service import SpellSyncService
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.push_abort import PushAbort
from spell_sync.push_journal import JournalLoadStatus
from spell_sync.push_prepared import PreparedPush
from spell_sync.read_outcome import DictionaryReadResult, ReadStatus
from spell_sync.sync_models import PushResult
from spell_sync.sync_run import SyncRun


def _pull_scope(wordlist: str = "/tmp/w.txt"):
    ctx = MagicMock()
    ctx.wordlist_str = wordlist
    ctx.wordlist_file = Path(wordlist)
    validated = MagicMock()
    validated.context = ctx
    return validated


class TestPhase4FacadeCoverage(unittest.TestCase):
    def test_build_pull_preview_error_and_skip_statuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            ok_dict = root / "ok.txt"
            corrupt = root / "corrupt.json"
            missing_path = root / "gone.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            ok_dict.write_text("alpha\nbeta\n", encoding="utf-8")
            corrupt.write_text("{not-json", encoding="utf-8")
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[
                    Dictionary("ok", str(ok_dict), DictionaryFormat.TEXT),
                    Dictionary("corrupt", str(corrupt), DictionaryFormat.JSON),
                    Dictionary("missing", str(missing_path), DictionaryFormat.TEXT),
                ],
            )
            preview = build_pull_preview(run)
            self.assertGreaterEqual(preview.additions, 1)
            self.assertIn("corrupt", preview.sources_skipped)

            with patch.object(SyncRun, "check_wordlist", return_value=ExitCode.WORDLIST_UNREADABLE):
                bad = SyncRun(wordlist=root / "nope.txt", dictionaries=[])
                blocked = build_pull_preview(bad)
            self.assertIsNotNone(blocked.wordlist_error)
            self.assertEqual(blocked.plan_identifier, "unavailable")

            unreadable = root / "locked.txt"
            unreadable.write_text("secret\n", encoding="utf-8")
            unreadable.chmod(0o000)
            try:
                locked_run = SyncRun(
                    wordlist=wordlist,
                    dictionaries=[
                        Dictionary("locked", str(unreadable), DictionaryFormat.TEXT),
                    ],
                )
                locked_preview = build_pull_preview(locked_run)
                self.assertIn("locked", locked_preview.sources_skipped)
            finally:
                unreadable.chmod(0o644)

            with patch(
                "spell_sync.application.builders.dictionary_read_result",
                return_value=DictionaryReadResult(
                    ReadStatus.UNSUPPORTED,
                    frozenset(),
                    "unsupported",
                    None,
                ),
            ):
                unsupported = build_pull_preview(run)
            self.assertIn("ok", unsupported.sources_skipped)

            with patch(
                "spell_sync.read_outcome.is_readable_for_union",
                return_value=False,
            ):
                with patch(
                    "spell_sync.application.builders.dictionary_read_result",
                    return_value=DictionaryReadResult(
                        ReadStatus.OK,
                        frozenset({"gamma"}),
                        None,
                        None,
                    ),
                ):
                    odd = build_pull_preview(run)
            self.assertTrue(odd.sources_skipped)

    def test_build_target_updates_and_push_reports(self):
        preview = PushPreview(
            prepared=None,
            targets=(TargetPreview("chrome", 1, 0, "Ready"),),
            additions=1,
            removals=0,
            warnings=(),
            created_at="t",
            plan_identifier="p",
            targets_to_update=1,
            unchanged=0,
            skipped=("jetbrains",),
            corrupt=("safari",),
            blocked=(),
        )
        rows = build_target_updates_from_preview(preview)
        names = {row.name for row in rows}
        self.assertEqual(names, {"chrome", "jetbrains", "safari"})

        stopped = build_push_operation_report(
            PushExecution(
                prepared=None,
                result=ExitCode.PUSH_ABORT,
                outcome=OperationOutcome.STOPPED_SAFELY,
                message="rolled back",
                plan_identifier="p",
            )
        )
        self.assertEqual(stopped.title, "Push stopped safely")
        self.assertIn("restored", stopped.summary.lower())

        failed = build_push_operation_report(
            PushExecution(
                prepared=None,
                result=ExitCode.PUSH_ABORT,
                outcome=OperationOutcome.FAILED,
                message="nope",
                plan_identifier="p",
            )
        )
        self.assertEqual(failed.title, "Push failed")

    def test_service_pull_edge_paths(self):
        service = SpellSyncService()
        preview = PullPreview(
            wordlist_path="/tmp/w.txt",
            additions=0,
            before_count=0,
            after_count=0,
            sources_used=(),
            sources_skipped=(),
            source_rows=(),
            warnings=(),
            created_at="t",
            plan_identifier="p1",
            merged_words=(),
            wordlist_error=ExitCode.PUSH_ABORT,
        )
        blocked = service.execute_pull(
            PullRequest(project=ProjectRef()), preview, confirmed_plan_id="p1"
        )
        self.assertEqual(blocked.outcome, OperationOutcome.FAILED)

        good = PullPreview(
            wordlist_path="/tmp/w.txt",
            additions=1,
            before_count=1,
            after_count=2,
            sources_used=("a",),
            sources_skipped=(),
            source_rows=(),
            warnings=(),
            created_at="t",
            plan_identifier="p1",
            merged_words=("a", "b"),
            wordlist_fingerprint="abc",
        )
        with patch(
            "spell_sync.application.service.command_helpers.mutating_command_scope_for"
        ) as scope:
            scope.return_value.__enter__.return_value = int(ExitCode.PUSH_ABORT)
            scope.return_value.__exit__.return_value = False
            locked = service.execute_pull(
                PullRequest(project=ProjectRef()), good, confirmed_plan_id="p1"
            )
        self.assertEqual(locked.outcome, OperationOutcome.FAILED)

        with patch(
            "spell_sync.application.service.command_helpers.mutating_command_scope_for"
        ) as scope:
            scope.return_value.__enter__.return_value = _pull_scope()
            scope.return_value.__exit__.return_value = False
            with patch.object(
                SyncRun,
                "execute_prepared_pull",
                return_value=ExitCode.PUSH_ABORT,
            ):
                with patch(
                    "spell_sync.application.service.file_content_hash",
                    return_value="changed",
                ):
                    conflict = service.execute_pull(
                        PullRequest(project=ProjectRef()), good, confirmed_plan_id="p1"
                    )
        self.assertEqual(conflict.outcome, OperationOutcome.STOPPED_SAFELY)

        with patch(
            "spell_sync.application.service.command_helpers.mutating_command_scope_for"
        ) as scope:
            scope.return_value.__enter__.return_value = _pull_scope()
            scope.return_value.__exit__.return_value = False
            with patch(
                "spell_sync.application.service.file_content_hash",
                return_value="abc",
            ):
                with patch.object(
                    SyncRun,
                    "execute_prepared_pull",
                    return_value=ExitCode.PUSH_ABORT,
                ):
                    write_fail = service.execute_pull(
                        PullRequest(project=ProjectRef()),
                        good,
                        confirmed_plan_id="p1",
                    )
        self.assertEqual(write_fail.outcome, OperationOutcome.FAILED)

    def test_service_push_preview_edge_paths(self):
        service = SpellSyncService()
        empty = PushPreview(
            prepared=None,
            targets=(),
            additions=0,
            removals=0,
            warnings=(),
            created_at="t",
            plan_identifier="p1",
            targets_to_update=0,
            unchanged=0,
            skipped=(),
            corrupt=(),
            blocked=(),
        )
        self.assertEqual(
            service.execute_push_preview(
                PushRequest(project=ProjectRef()),
                empty,
                confirmed_plan_id="p1",
            ).outcome,
            OperationOutcome.FAILED,
        )

        prepared = MagicMock(spec=PreparedPush)
        prepared.targets = ()
        prepared.wordlist_needs_write = True
        prepared.ctx = MagicMock(wordlist_str="/tmp/w.txt")
        target = MagicMock()
        target.planned.dictionary.name = "chrome"
        prepared.targets = (target,)
        preview = PushPreview(
            prepared=prepared,
            targets=(TargetPreview("chrome", 1, 0, "Ready"),),
            additions=1,
            removals=0,
            warnings=(),
            created_at="t",
            plan_identifier="p1",
            targets_to_update=1,
            unchanged=0,
            skipped=(),
            corrupt=(),
            blocked=(),
        )
        mismatch = service.execute_push_preview(
            PushRequest(project=ProjectRef()),
            preview,
            confirmed_plan_id="other",
        )
        self.assertEqual(mismatch.outcome, OperationOutcome.FAILED)

        with patch(
            "spell_sync.application.service.command_helpers.mutating_command_scope_for"
        ) as scope:
            scope.return_value.__enter__.return_value = int(ExitCode.PUSH_ABORT)
            scope.return_value.__exit__.return_value = False
            locked = service.execute_push_preview(
                PushRequest(project=ProjectRef()),
                preview,
                confirmed_plan_id="p1",
            )
        self.assertEqual(locked.outcome, OperationOutcome.FAILED)

        abort = PushAbort(ExitCode.PUSH_ABORT, "write_failed", "boom")
        with patch(
            "spell_sync.application.service.command_helpers.mutating_command_scope_for"
        ) as scope:
            scope.return_value.__enter__.return_value = MagicMock()
            scope.return_value.__exit__.return_value = False
            with patch(
                "spell_sync.application.service.plan_fingerprint_conflict",
                return_value=None,
            ):
                with patch(
                    "spell_sync.application.service.execute_prepared_push",
                    return_value=abort,
                ):
                    with patch(
                        "spell_sync.application.service.load_journal_result",
                    ) as journal:
                        journal.return_value.status = JournalLoadStatus.ABSENT
                        stopped = service.execute_push_preview(
                            PushRequest(project=ProjectRef()),
                            preview,
                            confirmed_plan_id="p1",
                        )
        self.assertEqual(stopped.outcome, OperationOutcome.STOPPED_SAFELY)

        recovery_abort = PushAbort(
            ExitCode.PUSH_ABORT,
            "rollback_incomplete",
            "incomplete",
        )
        with patch(
            "spell_sync.application.service.command_helpers.mutating_command_scope_for"
        ) as scope:
            scope.return_value.__enter__.return_value = MagicMock()
            scope.return_value.__exit__.return_value = False
            with patch(
                "spell_sync.application.service.plan_fingerprint_conflict",
                return_value=None,
            ):
                with patch(
                    "spell_sync.application.service.execute_prepared_push",
                    return_value=recovery_abort,
                ):
                    recovering = service.execute_push_preview(
                        PushRequest(project=ProjectRef()),
                        preview,
                        confirmed_plan_id="p1",
                    )
        self.assertEqual(recovering.outcome, OperationOutcome.RECOVERY_REQUIRED)

        with patch(
            "spell_sync.application.service.command_helpers.mutating_command_scope_for"
        ) as scope:
            scope.return_value.__enter__.return_value = MagicMock()
            scope.return_value.__exit__.return_value = False
            with patch(
                "spell_sync.application.service.plan_fingerprint_conflict",
                return_value=None,
            ):
                with patch(
                    "spell_sync.application.service.execute_prepared_push",
                    return_value=ExitCode.PUSH_ABORT,
                ):
                    with patch(
                        "spell_sync.application.service.load_journal_result",
                    ) as journal:
                        journal.return_value.status = JournalLoadStatus.VALID_IN_PROGRESS
                        exit_recovery = service.execute_push_preview(
                            PushRequest(project=ProjectRef()),
                            preview,
                            confirmed_plan_id="p1",
                        )
        self.assertEqual(exit_recovery.outcome, OperationOutcome.RECOVERY_REQUIRED)

        skipped = PushResult(
            word_count=1,
            written=("chrome",),
            skipped=("jetbrains",),
            skipped_reasons={"jetbrains": "running"},
        )
        with patch(
            "spell_sync.application.service.command_helpers.mutating_command_scope_for"
        ) as scope:
            scope.return_value.__enter__.return_value = MagicMock()
            scope.return_value.__exit__.return_value = False
            with patch(
                "spell_sync.application.service.plan_fingerprint_conflict",
                return_value=None,
            ):
                with patch(
                    "spell_sync.application.service.execute_prepared_push",
                    return_value=skipped,
                ):
                    warn = service.execute_push_preview(
                        PushRequest(project=ProjectRef()),
                        preview,
                        confirmed_plan_id="p1",
                    )
        self.assertEqual(warn.outcome, OperationOutcome.COMPLETED_WITH_WARNINGS)
        self.assertTrue(any("jetbrains" in item for item in warn.warnings))

        report = service.build_push_report(warn)
        self.assertEqual(report.operation, "push")
        pull_exec = PullExecution(
            preview=PullPreview(
                wordlist_path="/tmp/w.txt",
                additions=1,
                before_count=1,
                after_count=2,
                sources_used=("a",),
                sources_skipped=(),
                source_rows=(),
                warnings=(),
                created_at="t",
                plan_identifier="p",
                merged_words=("a", "b"),
            ),
            result=(1, 2),
            outcome=OperationOutcome.COMPLETED,
            message="ok",
        )
        self.assertEqual(service.build_pull_report(pull_exec).operation, "pull")

    def test_run_push_for_run_outcome_branches(self):
        service = SpellSyncService()
        prepared = MagicMock(spec=PreparedPush)
        run = MagicMock()
        with patch.object(
            service,
            "_execute_push_for_run",
            return_value=ExitCode.PUSH_ABORT,
        ):
            failed = service._run_push_for_run(run, prepared, dry_run=False)
        self.assertEqual(failed.outcome, OperationOutcome.FAILED)
        with patch.object(
            service,
            "_execute_push_for_run",
            return_value=PushResult(word_count=1, written=("a",), skipped=("b",)),
        ):
            warned = service._run_push_for_run(run, prepared, dry_run=False)
        self.assertEqual(warned.outcome, OperationOutcome.COMPLETED_WITH_WARNINGS)


if __name__ == "__main__":
    unittest.main()
