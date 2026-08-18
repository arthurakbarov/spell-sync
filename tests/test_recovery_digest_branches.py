"""Cover Recovery digest/txn mismatch and discard edge paths for publish CI."""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from spell_sync.application.reports import RecoveryOutcome, RecoveryStatus
from spell_sync.application.requests import ProjectRef, RecoveryRequest
from spell_sync.application.service import SpellSyncService
from spell_sync.exit_codes import ExitCode
from spell_sync.push_journal import (
    DiscardArtifactsResult,
    JournalLoadResult,
    JournalLoadStatus,
)
from tests.tui.fake_service import sample_recovery_preview


class TestRecoveryDigestBranches(unittest.TestCase):
    def test_recover_txn_mismatch_when_digest_matches(self) -> None:
        service = SpellSyncService()
        preview = sample_recovery_preview(
            transaction_id="txn-a",
            preview_fingerprint="digest-same",
        )
        journal = MagicMock()
        journal.transaction_id = "txn-b"
        scope = MagicMock()
        scope.context.wordlist_file = Path("/tmp/w.txt")
        scope.journal_result = JournalLoadResult(
            JournalLoadStatus.VALID_IN_PROGRESS,
            journal,
            content_digest="digest-same",
        )
        with patch(
            "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
        ) as mutating:
            mutating.return_value.__enter__.return_value = scope
            mutating.return_value.__exit__.return_value = False
            result = service.execute_recovery(
                RecoveryRequest(project=ProjectRef()),
                preview,
                confirmed_transaction_id=preview.preview_fingerprint,
            )
        self.assertEqual(result.outcome, RecoveryOutcome.FAILED)
        self.assertIn("changed", result.message.lower())

    def test_cleanup_txn_mismatch_and_discard_failure(self) -> None:
        service = SpellSyncService()
        preview = sample_recovery_preview(
            status=RecoveryStatus.COMPLETED_CLEANUP_PENDING,
            can_cleanup=True,
            transaction_id="txn-a",
            preview_fingerprint="digest-same",
        )
        journal = MagicMock()
        journal.transaction_id = "txn-b"
        scope = MagicMock()
        scope.context.wordlist_file = Path("/tmp/w.txt")
        scope.journal_result = JournalLoadResult(
            JournalLoadStatus.VALID_COMPLETED,
            journal,
            content_digest="digest-same",
        )
        with patch(
            "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
        ) as mutating:
            mutating.return_value.__enter__.return_value = scope
            mutating.return_value.__exit__.return_value = False
            txn_mismatch = service.execute_recovery_cleanup(
                RecoveryRequest(project=ProjectRef()),
                preview,
                confirmed_transaction_id=preview.preview_fingerprint,
            )
        self.assertEqual(txn_mismatch.outcome, RecoveryOutcome.FAILED)

        journal.transaction_id = "txn-a"
        with patch(
            "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
        ) as mutating:
            mutating.return_value.__enter__.return_value = scope
            mutating.return_value.__exit__.return_value = False
            with patch(
                "spell_sync.application._operation_deps.discard_completed_journal",
                return_value=DiscardArtifactsResult(False, False, "cleanup boom"),
            ):
                discard_fail = service.execute_recovery_cleanup(
                    RecoveryRequest(project=ProjectRef()),
                    preview,
                    confirmed_transaction_id=preview.preview_fingerprint,
                )
        self.assertEqual(discard_fail.outcome, RecoveryOutcome.FAILED)
        self.assertIn("cleanup", discard_fail.message.lower())

    def test_discard_corrupt_absent_digest_and_failures(self) -> None:
        service = SpellSyncService()
        preview = sample_recovery_preview(
            status=RecoveryStatus.CORRUPT_JOURNAL,
            can_discard=True,
            can_recover=False,
            preview_fingerprint="digest-corrupt",
        )
        scope = MagicMock()
        scope.context.wordlist_file = Path("/tmp/w.txt")

        scope.journal_result = JournalLoadResult(JournalLoadStatus.ABSENT, None)
        with patch(
            "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
        ) as mutating:
            mutating.return_value.__enter__.return_value = scope
            mutating.return_value.__exit__.return_value = False
            already_gone = service.execute_recovery_discard(
                RecoveryRequest(project=ProjectRef()),
                preview,
                confirmed_transaction_id=preview.preview_fingerprint,
            )
        self.assertEqual(already_gone.outcome, RecoveryOutcome.DISCARDED)

        scope.journal_result = JournalLoadResult(
            JournalLoadStatus.CORRUPT,
            None,
            detail="bad",
            content_digest="other-digest",
        )
        with patch(
            "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
        ) as mutating:
            mutating.return_value.__enter__.return_value = scope
            mutating.return_value.__exit__.return_value = False
            digest_mismatch = service.execute_recovery_discard(
                RecoveryRequest(project=ProjectRef()),
                preview,
                confirmed_transaction_id=preview.preview_fingerprint,
            )
        self.assertEqual(digest_mismatch.outcome, RecoveryOutcome.FAILED)

        scope.journal_result = JournalLoadResult(
            JournalLoadStatus.CORRUPT,
            None,
            detail="bad",
            content_digest=preview.preview_fingerprint,
        )
        with patch(
            "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
        ) as mutating:
            mutating.return_value.__enter__.return_value = scope
            mutating.return_value.__exit__.return_value = False
            with patch(
                "spell_sync.application._operation_deps.safe_discard_journal_file",
                return_value=(False, "cannot remove"),
            ):
                discard_fail = service.execute_recovery_discard(
                    RecoveryRequest(project=ProjectRef()),
                    preview,
                    confirmed_transaction_id=preview.preview_fingerprint,
                )
        self.assertEqual(discard_fail.outcome, RecoveryOutcome.FAILED)

        completed_preview = sample_recovery_preview(
            status=RecoveryStatus.RECOVERABLE,
            can_discard=True,
            preview_fingerprint="digest-completed",
        )
        scope.journal_result = JournalLoadResult(
            JournalLoadStatus.VALID_IN_PROGRESS,
            MagicMock(),
            content_digest="digest-completed",
        )
        with patch(
            "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
        ) as mutating:
            mutating.return_value.__enter__.return_value = scope
            mutating.return_value.__exit__.return_value = False
            wrong_status = service.execute_recovery_discard(
                RecoveryRequest(project=ProjectRef()),
                completed_preview,
                confirmed_transaction_id=completed_preview.preview_fingerprint,
            )
        self.assertEqual(wrong_status.outcome, RecoveryOutcome.FAILED)
        self.assertEqual(wrong_status.result, ExitCode.PUSH_ABORT)

    def test_discard_inert_unfinished_journal(self) -> None:
        service = SpellSyncService()
        preview = sample_recovery_preview(
            status=RecoveryStatus.RECOVERABLE,
            can_recover=False,
            can_discard=True,
            recoverable_count=0,
            conflict_count=0,
            failure_count=0,
            preview_fingerprint="digest-inert",
        )
        journal = MagicMock()
        scope = MagicMock()
        scope.context.wordlist_file = Path("/tmp/w.txt")
        scope.journal_result = JournalLoadResult(
            JournalLoadStatus.VALID_IN_PROGRESS,
            journal,
            content_digest="digest-inert",
        )
        with patch(
            "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
        ) as mutating:
            mutating.return_value.__enter__.return_value = scope
            mutating.return_value.__exit__.return_value = False
            with patch(
                "spell_sync.application._operation_deps.plan_recovery_from_journal",
                return_value=(),
            ):
                with patch(
                    "spell_sync.application._operation_deps.cleanup_after_successful_recovery",
                    return_value=DiscardArtifactsResult(True, True),
                ):
                    discarded = service.execute_recovery_discard(
                        RecoveryRequest(project=ProjectRef()),
                        preview,
                        confirmed_transaction_id=preview.preview_fingerprint,
                    )
        self.assertEqual(discarded.outcome, RecoveryOutcome.DISCARDED)

    def test_discard_unsupported_schema_journal(self) -> None:
        service = SpellSyncService()
        preview = sample_recovery_preview(
            status=RecoveryStatus.UNSUPPORTED_SCHEMA,
            can_recover=False,
            can_discard=True,
            recoverable_count=0,
            preview_fingerprint="digest-unsupported",
        )
        scope = MagicMock()
        scope.context.wordlist_file = Path("/tmp/w.txt")
        scope.journal_result = JournalLoadResult(
            JournalLoadStatus.UNSUPPORTED_SCHEMA,
            None,
            content_digest="digest-unsupported",
        )
        with patch(
            "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
        ) as mutating:
            mutating.return_value.__enter__.return_value = scope
            mutating.return_value.__exit__.return_value = False
            with patch(
                "spell_sync.application._operation_deps.safe_discard_journal_file",
                return_value=(True, None),
            ):
                discarded = service.execute_recovery_discard(
                    RecoveryRequest(project=ProjectRef()),
                    preview,
                    confirmed_transaction_id=preview.preview_fingerprint,
                )
        self.assertEqual(discarded.outcome, RecoveryOutcome.DISCARDED)
