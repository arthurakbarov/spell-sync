"""Application-level review session helpers."""

import unittest

from spell_sync.application.reports import OperationOutcome, OperationReport
from spell_sync.application.review_session import (
    ReviewSession,
    build_review_session_report,
)
from tests.tui.fake_service import sample_preview


class TestReviewSessionHelpers(unittest.TestCase):
    def test_pull_skipped_status(self):
        session = ReviewSession(pull_skipped=True)
        report = build_review_session_report(session)
        self.assertEqual(report.pull_status, "Skipped")
        self.assertRegex("\n".join(report.summary_lines), r"Collect my words:\s+Skipped")
        self.assertFalse(report.is_matched)

    def test_pull_completed_status(self):
        session = ReviewSession(
            pull_report=OperationReport(
                operation="pull",
                outcome=OperationOutcome.COMPLETED,
                title="Collect my words completed",
                summary="added words",
            )
        )
        report = build_review_session_report(session)
        self.assertEqual(report.pull_status, "Completed")

    def test_push_skipped_status(self):
        session = ReviewSession(pull_skipped=True, push_skipped=True)
        report = build_review_session_report(session)
        self.assertEqual(report.push_status, "Skipped")

    def test_push_no_changes_from_preview(self):
        from spell_sync.application.reports import PushPreview

        session = ReviewSession(
            pull_skipped=True,
            push_preview=PushPreview(
                prepared=None,
                targets=(),
                additions=0,
                removals=0,
                warnings=(),
                created_at="2026-01-01T00:00:00+00:00",
                plan_identifier="plan-1",
                targets_to_update=0,
                unchanged=1,
                skipped=(),
                corrupt=(),
                blocked=(),
            ),
        )
        report = build_review_session_report(session)
        self.assertEqual(report.push_status, "Not started")

    def test_recovery_required_note(self):
        session = ReviewSession(
            push_report=OperationReport(
                operation="push",
                outcome=OperationOutcome.RECOVERY_REQUIRED,
                title="Push failed",
                summary="rollback incomplete",
                recovery_required=True,
            )
        )
        report = build_review_session_report(session)
        self.assertIn("Recovery is required", report.recovery_note)

    def test_no_recovery_note(self):
        session = ReviewSession(pull_skipped=True, push_skipped=True)
        report = build_review_session_report(session)
        self.assertEqual(report.recovery_note, "No recovery is required.")

    def test_pull_recovery_and_stopped_status(self):
        session = ReviewSession(
            pull_report=OperationReport(
                operation="pull",
                outcome=OperationOutcome.RECOVERY_REQUIRED,
                title="Pull failed",
                summary="bad",
            )
        )
        self.assertEqual(build_review_session_report(session).pull_status, "Recovery required")
        session2 = ReviewSession(
            pull_report=OperationReport(
                operation="pull",
                outcome=OperationOutcome.STOPPED_SAFELY,
                title="Pull stopped",
                summary="conflict",
            )
        )
        self.assertEqual(build_review_session_report(session2).pull_status, "Stopped safely")

    def test_push_no_changes_from_report_and_preview(self):
        from spell_sync.application.reports import PushPreview, TargetUpdateReport

        preview = PushPreview(
            prepared=sample_preview().prepared,
            targets=(),
            additions=0,
            removals=0,
            warnings=(),
            created_at="2026-01-01T00:00:00+00:00",
            plan_identifier="plan-1",
            targets_to_update=0,
            unchanged=1,
            skipped=(),
            corrupt=(),
            blocked=(),
        )
        session = ReviewSession(pull_skipped=True, push_preview=preview)
        self.assertEqual(build_review_session_report(session).push_status, "No changes")
        session2 = ReviewSession(
            push_report=OperationReport(
                operation="push",
                outcome=OperationOutcome.COMPLETED,
                title="Update my apps completed",
                summary="none",
                target_updates=(TargetUpdateReport("chrome", 0, 0, "Unchanged"),),
            )
        )
        self.assertEqual(build_review_session_report(session2).push_status, "No changes")

    def test_push_warning_and_recovery_status(self):
        session = ReviewSession(
            push_report=OperationReport(
                operation="push",
                outcome=OperationOutcome.COMPLETED_WITH_WARNINGS,
                title="Update my apps completed",
                summary="warn",
            )
        )
        self.assertEqual(
            build_review_session_report(session).push_status,
            "Completed with warnings",
        )
        session2 = ReviewSession(
            push_report=OperationReport(
                operation="push",
                outcome=OperationOutcome.RECOVERY_REQUIRED,
                title="Push failed",
                summary="bad",
                recovery_required=True,
            )
        )
        self.assertEqual(build_review_session_report(session2).push_status, "Recovery required")
        session = ReviewSession(
            pull_report=OperationReport(
                operation="pull",
                outcome=OperationOutcome.COMPLETED_WITH_WARNINGS,
                title="Collect my words completed",
                summary="warn",
            )
        )
        report = build_review_session_report(session)
        self.assertEqual(report.pull_status, "Completed with warnings")
        self.assertFalse(report.is_matched)

    def test_push_status_variants(self):
        session = ReviewSession(
            push_report=OperationReport(
                operation="push",
                outcome=OperationOutcome.STOPPED_SAFELY,
                title="Push stopped",
                summary="conflict",
            )
        )
        self.assertEqual(build_review_session_report(session).push_status, "Stopped safely")
        session2 = ReviewSession(
            push_report=OperationReport(
                operation="push",
                outcome=OperationOutcome.FAILED,
                title="Push failed",
                summary="bad",
            )
        )
        self.assertEqual(build_review_session_report(session2).push_status, "Failed")

    def test_matched_requires_clean_pull_and_push(self):
        session = ReviewSession(
            pull_report=OperationReport(
                operation="pull",
                outcome=OperationOutcome.COMPLETED,
                title="Collect my words completed",
                summary="ok",
            ),
            push_report=OperationReport(
                operation="push",
                outcome=OperationOutcome.COMPLETED,
                title="Update my apps completed",
                summary="ok",
            ),
        )
        self.assertTrue(build_review_session_report(session).is_matched)
        warnings = ReviewSession(
            pull_report=OperationReport(
                operation="pull",
                outcome=OperationOutcome.COMPLETED,
                title="Collect my words completed",
                summary="ok",
            ),
            push_report=OperationReport(
                operation="push",
                outcome=OperationOutcome.COMPLETED_WITH_WARNINGS,
                title="Update my apps completed",
                summary="skipped running app",
            ),
        )
        self.assertFalse(build_review_session_report(warnings).is_matched)

    def test_session_is_not_frozen(self):
        session = ReviewSession()
        session.pull_skipped = True
        self.assertTrue(session.pull_skipped)


if __name__ == "__main__":
    unittest.main()
