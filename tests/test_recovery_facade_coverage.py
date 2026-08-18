"""Coverage for recovery facade, builders, and planning helpers."""

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

from spell_sync.application.operation_reports import build_recovery_operation_report
from spell_sync.application.recovery_preview_builders import build_recovery_preview
from spell_sync.application.reports import (
    OperationOutcome,
    RecoveryExecution,
    RecoveryOutcome,
    RecoveryStatus,
)
from spell_sync.application.requests import (
    ProjectRef,
    RecoveryRequest,
)
from spell_sync.application.service import SpellSyncService
from spell_sync.exit_codes import ExitCode
from spell_sync.push_journal import (
    JOURNAL_STATE_COMPLETED,
    JOURNAL_STATE_ROLLBACK_INCOMPLETE,
    DiscardArtifactsResult,
    JournalLoadResult,
    JournalLoadStatus,
    RecoverResult,
    plan_recovery_from_journal,
)
from spell_sync.resolved_runtime import ResolvedRuntime
from spell_sync.settings import ConfigLoadResult, ConfigStatus
from tests.journal_test_utils import write_restore_scenario_journal, write_test_journal
from tests.tui.fake_service import sample_recovery_preview


def _recovery_scope(
    wordlist: Path,
    *,
    journal_status: JournalLoadStatus = JournalLoadStatus.VALID_IN_PROGRESS,
    journal=None,
    content_digest: str | None = None,
):
    ctx = MagicMock()
    ctx.wordlist_file = wordlist
    ctx.wordlist_str = str(wordlist)
    digest = content_digest
    if digest is None and journal is not None:
        tid = getattr(journal, "transaction_id", None)
        if isinstance(tid, str):
            digest = tid
    journal_result = JournalLoadResult(
        status=journal_status,
        journal=journal,
        detail=None,
        content_digest=digest,
    )
    validated = MagicMock(spec=ResolvedRuntime)
    validated.context = ctx
    validated.journal_result = journal_result
    return validated


class TestRecoveryFacadeCoverage(unittest.TestCase):
    def test_execute_recovery_guard_paths(self):
        service = SpellSyncService()
        preview = sample_recovery_preview()
        mismatch = service.execute_recovery(
            RecoveryRequest(project=ProjectRef()),
            preview,
            confirmed_transaction_id="wrong",
        )
        self.assertEqual(mismatch.outcome, RecoveryOutcome.FAILED)

        blocked = service.execute_recovery(
            RecoveryRequest(project=ProjectRef()),
            replace(preview, can_recover=False),
            confirmed_transaction_id=preview.preview_fingerprint,
        )
        self.assertEqual(blocked.outcome, RecoveryOutcome.FAILED)

        with patch(
            "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
        ) as scope:
            scope.return_value.__enter__.return_value = int(ExitCode.PUSH_ABORT)
            scope.return_value.__exit__.return_value = False
            locked = service.execute_recovery(
                RecoveryRequest(project=ProjectRef()),
                preview,
                confirmed_transaction_id=preview.preview_fingerprint,
            )
        self.assertEqual(locked.outcome, RecoveryOutcome.FAILED)

    def test_execute_recovery_journal_changed(self):
        service = SpellSyncService()
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            dictionary = Path(tmp) / "dict.txt"
            journal = write_restore_scenario_journal(wordlist, dictionary)
            preview = sample_recovery_preview(
                transaction_id="stale-id",
                preview_fingerprint="stale-id",
            )
            scope = _recovery_scope(wordlist, journal=journal)
            with patch(
                "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
            ) as mutating:
                mutating.return_value.__enter__.return_value = scope
                mutating.return_value.__exit__.return_value = False
                changed = service.execute_recovery(
                    RecoveryRequest(project=ProjectRef(wordlist=wordlist)),
                    preview,
                    confirmed_transaction_id=preview.preview_fingerprint,
                )
            self.assertEqual(changed.outcome, RecoveryOutcome.FAILED)
            self.assertIn("changed", changed.message.lower())

    def test_execute_recovery_conflict_and_incomplete(self):
        service = SpellSyncService()
        preview = sample_recovery_preview()
        journal = MagicMock()
        journal.transaction_id = preview.transaction_id
        conflict_result = RecoverResult(
            restored=(),
            skipped=(),
            failed=(),
            conflicts=("vscode",),
        )
        incomplete_result = RecoverResult(
            restored=("wordlist",),
            skipped=(),
            failed=("chrome",),
            conflicts=(),
        )
        scope = _recovery_scope(Path("/tmp/w.txt"), journal=journal)
        with patch(
            "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
        ) as mutating:
            mutating.return_value.__enter__.return_value = scope
            mutating.return_value.__exit__.return_value = False
            with patch(
                "spell_sync.application._operation_deps.recover_from_journal",
                return_value=conflict_result,
            ):
                conflict = service.execute_recovery(
                    RecoveryRequest(project=ProjectRef()),
                    preview,
                    confirmed_transaction_id=preview.preview_fingerprint,
                )
            self.assertEqual(conflict.outcome, RecoveryOutcome.CONFLICTED)

            with patch(
                "spell_sync.application._operation_deps.recover_from_journal",
                return_value=incomplete_result,
            ):
                incomplete = service.execute_recovery(
                    RecoveryRequest(project=ProjectRef()),
                    preview,
                    confirmed_transaction_id=preview.preview_fingerprint,
                )
            self.assertEqual(incomplete.outcome, RecoveryOutcome.RECOVERY_INCOMPLETE)

    def test_execute_recovery_success_with_skipped(self):
        service = SpellSyncService()
        preview = sample_recovery_preview()
        journal = MagicMock()
        journal.transaction_id = preview.transaction_id
        result = RecoverResult(
            restored=("wordlist",),
            skipped=("chrome",),
            failed=(),
            conflicts=(),
        )
        scope = _recovery_scope(Path("/tmp/w.txt"), journal=journal)
        with patch(
            "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
        ) as mutating:
            mutating.return_value.__enter__.return_value = scope
            mutating.return_value.__exit__.return_value = False
            with patch(
                "spell_sync.application._operation_deps.recover_from_journal",
                return_value=result,
            ):
                with patch(
                    "spell_sync.application._operation_deps.cleanup_after_successful_recovery"
                ):
                    events: list = []
                    execution = service.execute_recovery(
                        RecoveryRequest(project=ProjectRef()),
                        preview,
                        confirmed_transaction_id=preview.preview_fingerprint,
                        event_sink=events.append,
                    )
        self.assertEqual(execution.outcome, RecoveryOutcome.RECOVERED_WITH_WARNINGS)

    def test_execute_recovery_cleanup_and_discard(self):
        service = SpellSyncService()
        cleanup_preview = sample_recovery_preview(
            status=RecoveryStatus.COMPLETED_CLEANUP_PENDING,
            can_recover=False,
            can_cleanup=True,
        )
        mismatch = service.execute_recovery_cleanup(
            RecoveryRequest(project=ProjectRef()),
            cleanup_preview,
            confirmed_transaction_id="wrong",
        )
        self.assertEqual(mismatch.outcome, RecoveryOutcome.FAILED)

        wrong_status = service.execute_recovery_cleanup(
            RecoveryRequest(project=ProjectRef()),
            sample_recovery_preview(),
            confirmed_transaction_id=sample_recovery_preview().preview_fingerprint,
        )
        self.assertEqual(wrong_status.outcome, RecoveryOutcome.FAILED)

        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            write_test_journal(
                wordlist,
                state=JOURNAL_STATE_COMPLETED,
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            scope = _recovery_scope(
                wordlist,
                journal_status=JournalLoadStatus.VALID_COMPLETED,
                journal=MagicMock(transaction_id=cleanup_preview.transaction_id),
                content_digest=cleanup_preview.preview_fingerprint,
            )
            with patch(
                "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
            ) as mutating:
                mutating.return_value.__enter__.return_value = scope
                mutating.return_value.__exit__.return_value = False
                with patch(
                    "spell_sync.application._operation_deps.discard_completed_journal"
                ) as discard:
                    discard.return_value = DiscardArtifactsResult(True, True, None)
                    cleaned = service.execute_recovery_cleanup(
                        RecoveryRequest(project=ProjectRef(wordlist=wordlist)),
                        cleanup_preview,
                        confirmed_transaction_id=cleanup_preview.preview_fingerprint,
                    )
            discard.assert_called_once()
            self.assertEqual(cleaned.outcome, RecoveryOutcome.CLEANUP_COMPLETED)

        discard_preview = sample_recovery_preview(
            status=RecoveryStatus.CORRUPT_JOURNAL,
            can_discard=True,
            can_recover=False,
        )
        with patch(
            "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
        ) as mutating:
            mutating.return_value.__enter__.return_value = _recovery_scope(
                Path("/tmp/w.txt"),
                journal_status=JournalLoadStatus.CORRUPT,
                content_digest=discard_preview.preview_fingerprint,
            )
            mutating.return_value.__exit__.return_value = False
            with patch(
                "spell_sync.application._operation_deps.safe_discard_journal_file",
                return_value=(True, None),
            ) as discard:
                discarded = service.execute_recovery_discard(
                    RecoveryRequest(project=ProjectRef()),
                    discard_preview,
                    confirmed_transaction_id=discard_preview.preview_fingerprint,
                )
        discard.assert_called_once()
        self.assertEqual(discarded.outcome, RecoveryOutcome.DISCARDED)

    def test_build_recovery_preview_statuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            ctx = MagicMock()
            ctx.wordlist_file = wordlist
            absent = ResolvedRuntime(
                context=ctx,
                config_result=ConfigLoadResult(ConfigStatus.VALID, {}, ()),
                journal_result=JournalLoadResult(JournalLoadStatus.ABSENT, None),
                identity=MagicMock(),
            )
            preview = build_recovery_preview(absent)
            self.assertEqual(preview.status, RecoveryStatus.ABSENT)

            corrupt = replace(
                absent,
                journal_result=JournalLoadResult(
                    JournalLoadStatus.CORRUPT,
                    None,
                    detail="bad json",
                ),
            )
            self.assertEqual(
                build_recovery_preview(corrupt).status,
                RecoveryStatus.CORRUPT_JOURNAL,
            )

            unsafe = replace(
                absent,
                journal_result=JournalLoadResult(
                    JournalLoadStatus.UNSAFE_ARTIFACT,
                    None,
                    detail="unsafe artifact",
                    content_digest=None,
                ),
            )
            unsafe_preview = build_recovery_preview(unsafe)
            self.assertEqual(unsafe_preview.status, RecoveryStatus.CORRUPT_JOURNAL)
            self.assertEqual(unsafe_preview.preview_fingerprint, "unsafe")

            unsupported = replace(
                absent,
                journal_result=JournalLoadResult(
                    JournalLoadStatus.UNSUPPORTED_SCHEMA,
                    None,
                    detail="schema 0",
                ),
            )
            unsupported_preview = build_recovery_preview(unsupported)
            self.assertEqual(
                unsupported_preview.status,
                RecoveryStatus.UNSUPPORTED_SCHEMA,
            )
            self.assertTrue(unsupported_preview.can_discard)

            journal = write_test_journal(
                wordlist,
                wordlist_write_started=True,
                wordlist_write_completed=True,
                state=JOURNAL_STATE_COMPLETED,
            )
            completed = replace(
                absent,
                journal_result=JournalLoadResult(
                    JournalLoadStatus.VALID_COMPLETED,
                    journal,
                ),
            )
            cleanup = build_recovery_preview(completed)
            self.assertEqual(cleanup.status, RecoveryStatus.COMPLETED_CLEANUP_PENDING)
            self.assertTrue(cleanup.can_cleanup)

            in_progress = replace(
                absent,
                journal_result=JournalLoadResult(
                    JournalLoadStatus.VALID_IN_PROGRESS,
                    write_restore_scenario_journal(wordlist, Path(tmp) / "dict.txt"),
                ),
            )
            recoverable = build_recovery_preview(in_progress)
            self.assertIn(
                recoverable.status,
                {RecoveryStatus.RECOVERABLE, RecoveryStatus.RECOVERY_IN_PROGRESS},
            )
            self.assertFalse(recoverable.can_discard)

            inert = replace(
                absent,
                journal_result=JournalLoadResult(
                    JournalLoadStatus.VALID_IN_PROGRESS,
                    write_test_journal(wordlist),
                ),
            )
            inert_preview = build_recovery_preview(inert)
            self.assertEqual(inert_preview.status, RecoveryStatus.RECOVERABLE)
            self.assertFalse(inert_preview.can_recover)
            self.assertTrue(inert_preview.can_discard)
            self.assertEqual(inert_preview.recoverable_count, 0)

    def test_build_recovery_operation_report_outcomes(self):
        preview = sample_recovery_preview()
        cases = [
            (
                RecoveryOutcome.RECOVERED,
                OperationOutcome.COMPLETED,
                "Recovery completed",
            ),
            (
                RecoveryOutcome.RECOVERED_WITH_WARNINGS,
                OperationOutcome.COMPLETED_WITH_WARNINGS,
                "warnings",
            ),
            (
                RecoveryOutcome.CONFLICTED,
                OperationOutcome.STOPPED_SAFELY,
                "stopped safely",
            ),
            (
                RecoveryOutcome.RECOVERY_INCOMPLETE,
                OperationOutcome.RECOVERY_REQUIRED,
                "incomplete",
            ),
            (
                RecoveryOutcome.CLEANUP_COMPLETED,
                OperationOutcome.COMPLETED,
                "cleanup completed",
            ),
            (
                RecoveryOutcome.DISCARDED,
                OperationOutcome.COMPLETED,
                "discarded",
            ),
            (
                RecoveryOutcome.FAILED,
                OperationOutcome.FAILED,
                "failed",
            ),
        ]
        for outcome, expected, title_part in cases:
            execution = RecoveryExecution(
                preview=preview,
                result=ExitCode.OK,
                outcome=outcome,
                message="message",
                restored=("wordlist",),
                skipped=("chrome",),
                conflicts=("vscode",),
                failed=("edge",),
            )
            report = build_recovery_operation_report(execution)
            self.assertEqual(report.outcome, expected)
            self.assertIn(title_part.lower(), report.title.lower())

    def test_plan_recovery_from_journal_branches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            created = root / "created.txt"
            wordlist.write_text("after\n", encoding="utf-8")
            created.write_text("created\n", encoding="utf-8")
            journal = write_test_journal(
                wordlist,
                targets=[],
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            plans = plan_recovery_from_journal(journal)
            self.assertTrue(plans)

            rollback_journal = write_test_journal(
                wordlist,
                state=JOURNAL_STATE_ROLLBACK_INCOMPLETE,
                wordlist_write_started=True,
                wordlist_write_completed=False,
            )
            rollback_plans = plan_recovery_from_journal(rollback_journal)
            self.assertTrue(rollback_plans)
            self.assertEqual(rollback_journal.state, JOURNAL_STATE_ROLLBACK_INCOMPLETE)

    def test_recovery_cleanup_failure_after_success(self):
        service = SpellSyncService()
        preview = sample_recovery_preview(status=RecoveryStatus.RECOVERABLE)
        with patch(
            "spell_sync.application._operation_deps.recover_from_journal",
            return_value=RecoverResult(("wordlist",), (), ()),
        ):
            with patch(
                "spell_sync.application._operation_deps.cleanup_after_successful_recovery",
                return_value=DiscardArtifactsResult(False, False, "cleanup failed"),
            ):
                with patch(
                    "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
                ) as scope:
                    scope.return_value.__enter__.return_value = MagicMock(
                        journal_result=MagicMock(
                            status=JournalLoadStatus.VALID_IN_PROGRESS,
                            journal=MagicMock(transaction_id=preview.transaction_id),
                            content_digest=preview.preview_fingerprint,
                        )
                    )
                    scope.return_value.__exit__.return_value = False
                    execution = service.execute_recovery(
                        RecoveryRequest(project=ProjectRef()),
                        preview,
                        confirmed_transaction_id=preview.preview_fingerprint,
                    )
        self.assertEqual(execution.outcome, RecoveryOutcome.RECOVERY_INCOMPLETE)

    def test_recovery_discard_corrupt_journal_failure(self):
        service = SpellSyncService()
        preview = sample_recovery_preview(
            status=RecoveryStatus.CORRUPT_JOURNAL,
            can_discard=True,
            can_recover=False,
        )
        with patch(
            "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
        ) as scope:
            scope.return_value.__enter__.return_value = MagicMock(
                context=MagicMock(wordlist_file=Path("/tmp/w.txt"))
            )
            scope.return_value.__exit__.return_value = False
            with patch(
                "spell_sync.application._operation_deps.safe_discard_journal_file",
                return_value=(False, "nope"),
            ):
                execution = service.execute_recovery_discard(
                    RecoveryRequest(project=ProjectRef()),
                    preview,
                    confirmed_transaction_id=preview.preview_fingerprint,
                )
        self.assertEqual(execution.outcome, RecoveryOutcome.FAILED)

    def test_recovery_cleanup_discard_failure(self):
        service = SpellSyncService()
        preview = sample_recovery_preview(status=RecoveryStatus.COMPLETED_CLEANUP_PENDING)
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
                "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
            ) as scope:
                scope.return_value.__enter__.return_value = MagicMock(
                    context=MagicMock(wordlist_file=wordlist),
                    journal_result=MagicMock(status=JournalLoadStatus.VALID_COMPLETED),
                )
                scope.return_value.__exit__.return_value = False
                with patch(
                    "spell_sync.application._operation_deps.discard_completed_journal",
                    return_value=DiscardArtifactsResult(False, False, "failed"),
                ):
                    execution = service.execute_recovery_cleanup(
                        RecoveryRequest(project=ProjectRef(wordlist=wordlist)),
                        preview,
                        confirmed_transaction_id=preview.preview_fingerprint,
                    )
            self.assertEqual(execution.outcome, RecoveryOutcome.FAILED)


if __name__ == "__main__":
    unittest.main()
