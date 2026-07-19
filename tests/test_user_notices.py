"""Tests for UserNotice catalog and operation explanations."""

from __future__ import annotations

import re
import unittest
from unittest.mock import MagicMock

from spell_sync.application.builders import (
    build_dashboard_issues,
    build_pull_operation_report,
    build_push_operation_report,
)
from spell_sync.application.operation_explanations import (
    build_push_target_updates,
    format_operation_report_text,
    format_pull_planned_actual_lines,
    format_push_planned_actual_lines,
    operation_report_notices,
    target_settings_blocker_notice,
)
from spell_sync.application.reports import (
    DashboardIssue,
    DashboardSeverity,
    OperationOutcome,
    OperationReport,
    PullExecution,
    PullPreview,
    PushExecution,
    PushPreview,
    StatusSnapshot,
    TargetPreview,
)
from spell_sync.application.user_notices import (
    NOTICE_CATALOG,
    build_notice,
    catalog_entry,
    dashboard_issue_to_notice,
    format_notice_action,
    format_notice_block,
    format_notice_details,
    format_notice_summary,
    format_notice_technical,
    format_skip_status,
    skip_reason_to_notice_code,
)
from spell_sync.settings import ConfigLoadResult, ConfigStatus
from spell_sync.sync_models import PushResult

_SENSITIVE_PATTERNS = (
    re.compile(r"/Users/"),
    re.compile(r"/home/"),
    re.compile(r"\balpha\b", re.I),
    re.compile(r"\bbeta\b", re.I),
    re.compile(r"\bsecret\b", re.I),
    re.compile(r"[a-f0-9]{32,}", re.I),
)


def _assert_notice_safe(text: str) -> None:
    for pattern in _SENSITIVE_PATTERNS:
        assert not pattern.search(text), f"unexpected sensitive content: {text!r}"


class TestUserNoticeCatalog(unittest.TestCase):
    REQUIRED_CODES = frozenset(
        {
            "invalid_config",
            "unreadable_wordlist",
            "pending_recovery",
            "corrupt_journal",
            "operation_locked",
            "target_corrupt",
            "target_unreadable",
            "application_running",
            "stale_preview",
            "external_change",
            "removal_confirmation_required",
            "rollback_incomplete",
            "history_write_failed",
        }
    )

    def test_catalog_contains_required_codes(self):
        self.assertTrue(self.REQUIRED_CODES.issubset(NOTICE_CATALOG))

    def test_catalog_entries_have_complete_text(self):
        for code in self.REQUIRED_CODES:
            entry = catalog_entry(code)
            self.assertTrue(entry.title)
            self.assertTrue(entry.explanation)
            self.assertTrue(entry.suggested_action)

    def test_build_notice_includes_technical_target(self):
        notice = build_notice("application_running", target_id="chrome")
        self.assertEqual(notice.code, "application_running")
        self.assertIn("reason=application_running", notice.technical_detail or "")
        self.assertIn("target=chrome", notice.technical_detail or "")

    def test_dashboard_issue_mapping_uses_catalog(self):
        issue = DashboardIssue(
            code="pending_recovery",
            severity=DashboardSeverity.BLOCKED,
            title="ignored",
            detail="ignored",
        )
        notice = dashboard_issue_to_notice(issue)
        catalog = catalog_entry("pending_recovery")
        self.assertEqual(notice.title, catalog.title)
        self.assertEqual(notice.explanation, catalog.explanation)
        self.assertEqual(notice.suggested_action, catalog.suggested_action)

    def test_dashboard_invalid_config_keeps_diagnostic_detail(self):
        issue = DashboardIssue(
            code="invalid_config",
            severity=DashboardSeverity.BLOCKED,
            title="Invalid configuration",
            detail="Missing dictionaries section.",
            suggested_action="Fix spell-sync.toml, then run spell-sync config-check.",
        )
        notice = dashboard_issue_to_notice(issue)
        self.assertEqual(notice.explanation, "Missing dictionaries section.")

    def test_skip_reason_maps_to_application_running(self):
        self.assertEqual(
            skip_reason_to_notice_code("Google Chrome is running"),
            "application_running",
        )
        self.assertIn("application was running", format_skip_status("Google Chrome is running"))

    def test_notice_formatting_layers(self):
        notice = build_notice("stale_preview", target_id="chrome")
        self.assertEqual(format_notice_summary(notice), notice.title)
        self.assertEqual(format_notice_details(notice), notice.explanation)
        self.assertTrue(format_notice_action(notice))
        self.assertIn("reason=stale_preview", format_notice_technical(notice))

    def test_notices_exclude_sensitive_content(self):
        for code in self.REQUIRED_CODES:
            notice = build_notice(code, target_id="chrome")
            block = format_notice_block(notice)
            _assert_notice_safe(block)

    def test_cli_and_tui_share_dashboard_catalog_text(self):
        from spell_sync.push_journal import JournalLoadResult, JournalLoadStatus

        validated = MagicMock()
        validated.config_result = ConfigLoadResult(
            ConfigStatus.SYNTAX_ERROR,
            None,
            (),
        )
        validated.journal_result = JournalLoadResult(JournalLoadStatus.ABSENT, None)
        snapshot = StatusSnapshot(
            wordlist_count=0,
            diffs=(),
            skipped_unreadable=(),
            skipped_corrupt=(),
        )
        issues = build_dashboard_issues(validated, snapshot, lock_info=None)
        invalid = next(issue for issue in issues if issue.code == "invalid_config")
        notice = dashboard_issue_to_notice(invalid)
        self.assertEqual(notice.title, catalog_entry("invalid_config").title)


class TestPlannedActualReports(unittest.TestCase):
    def _preview(self) -> PushPreview:
        return PushPreview(
            prepared=None,
            targets=(
                TargetPreview("chrome:Default", 12, 0, "Ready"),
                TargetPreview("cursor:Default", 8, 3, "Review"),
            ),
            additions=20,
            removals=3,
            warnings=(),
            created_at="2026-07-19T12:00:00+00:00",
            plan_identifier="abc12345",
            targets_to_update=2,
            unchanged=0,
            skipped=(),
            corrupt=(),
            blocked=(),
        )

    def test_push_planned_actual_format(self):
        preview = self._preview()
        result = PushResult(
            word_count=12,
            written=("chrome:Default",),
            skipped=("cursor:Default",),
            skipped_reasons={"cursor:Default": "Google Chrome is running"},
        )
        updates = build_push_target_updates(preview, result)
        lines = format_push_planned_actual_lines(preview, updates)
        text = "\n".join(lines)
        self.assertIn("Planned", text)
        self.assertIn("Actual", text)
        self.assertIn("Chrome", text)
        self.assertIn("Updated", text)
        self.assertIn("application was running", text)
        _assert_notice_safe(text)

    def test_pull_planned_actual_with_skipped_source(self):
        preview = PullPreview(
            wordlist_path="/tmp/wordlist.txt",
            additions=17,
            before_count=10,
            after_count=27,
            sources_used=("ok",),
            sources_skipped=("locked",),
            source_rows=(),
            warnings=(),
            created_at="2026-07-19T12:00:00+00:00",
            plan_identifier="plan1234",
            merged_words=tuple(f"word{i}" for i in range(27)),
        )
        execution = PullExecution(
            preview=preview,
            result=(10, 25),
            outcome=OperationOutcome.COMPLETED,
            message="done",
        )
        lines = format_pull_planned_actual_lines(preview, execution)
        text = "\n".join(lines)
        self.assertIn("Planned additions: 17", text)
        self.assertIn("Actual additions: 15", text)
        self.assertIn("Skipped sources: 1", text)
        self.assertIn("dictionary target could not be read", text)
        _assert_notice_safe(text)

    def test_push_operation_report_includes_planned_actual(self):
        preview = self._preview()
        result = PushResult(
            word_count=12,
            written=("chrome:Default",),
            skipped=("cursor:Default",),
            skipped_reasons={"cursor:Default": "Google Chrome is running"},
        )
        execution = PushExecution(
            prepared=None,
            result=result,
            outcome=OperationOutcome.COMPLETED_WITH_WARNINGS,
            target_updates=build_push_target_updates(preview, result),
            push_preview=preview,
            plan_identifier="abc12345",
        )
        report = build_push_operation_report(execution)
        text = format_operation_report_text(report)
        self.assertIn("Planned", text)
        self.assertIn("Actual", text)
        self.assertIn("Preview created:", text)
        _assert_notice_safe(text)

    def test_stale_preview_notice_on_conflict(self):
        preview = self._preview()
        execution = PushExecution(
            prepared=None,
            result=PushResult(word_count=0, written=()),
            outcome=OperationOutcome.STOPPED_SAFELY,
            conflict_target="chrome:Default",
            push_preview=preview,
            plan_identifier="abc12345",
        )
        report = build_push_operation_report(execution)
        notices = operation_report_notices(report)
        self.assertTrue(any(notice.code == "stale_preview" for notice in notices))

    def test_rollback_incomplete_notice(self):
        preview = self._preview()
        execution = PushExecution(
            prepared=None,
            result=PushResult(word_count=0, written=()),
            outcome=OperationOutcome.RECOVERY_REQUIRED,
            recovery_required=True,
            push_preview=preview,
            plan_identifier="abc12345",
        )
        report = build_push_operation_report(execution)
        self.assertEqual(report.title, "Rollback incomplete")
        self.assertTrue(report.recovery_required)

    def test_pull_operation_report_uses_planned_actual(self):
        preview = PullPreview(
            wordlist_path="/tmp/wordlist.txt",
            additions=3,
            before_count=1,
            after_count=4,
            sources_used=("a",),
            sources_skipped=(),
            source_rows=(),
            warnings=(),
            created_at="2026-07-19T12:00:00+00:00",
            plan_identifier="plan1234",
            merged_words=("a", "b", "c", "d"),
        )
        execution = PullExecution(
            preview=preview,
            result=(1, 4),
            outcome=OperationOutcome.COMPLETED,
            message="ok",
        )
        report = build_pull_operation_report(execution)
        text = format_operation_report_text(report)
        self.assertIn("Planned additions: 3", text)
        self.assertIn("Actual additions: 3", text)

    def test_target_settings_stale_preview_notice(self):
        notice = target_settings_blocker_notice(_STALE_CONFIG_MESSAGE)
        self.assertIsNotNone(notice)
        assert notice is not None
        self.assertEqual(notice.code, "stale_preview")

    def test_target_settings_invalid_config_notice(self):
        notice = target_settings_blocker_notice("Missing dictionaries section.")
        assert notice is not None
        self.assertEqual(notice.code, "invalid_config")

    def test_target_settings_blocker_without_error(self):
        self.assertIsNone(target_settings_blocker_notice(None))


class TestUserNoticeCoverage(unittest.TestCase):
    def test_unknown_catalog_code_raises(self):
        with self.assertRaises(KeyError):
            catalog_entry("not_a_real_code")

    def test_non_catalog_dashboard_issue(self):
        issue = DashboardIssue(
            code="empty_wordlist",
            severity=DashboardSeverity.WARNING,
            title="Wordlist is empty",
            detail="Push will abort.",
            suggested_action="Add words.",
        )
        notice = dashboard_issue_to_notice(issue)
        self.assertEqual(notice.code, "empty_wordlist")
        self.assertEqual(format_notice_technical(notice), "reason=empty_wordlist")

    def test_target_issue_mapping_extracts_target_ids(self):
        issue = DashboardIssue(
            code="skipped_unreadable",
            severity=DashboardSeverity.WARNING,
            title="Unreadable dictionary targets",
            detail="Affected targets: chrome:Default, macos-spelling.",
        )
        notice = dashboard_issue_to_notice(issue)
        self.assertIn("target=chrome,macos_spelling", notice.technical_detail or "")

    def test_skip_reason_branches(self):
        self.assertEqual(skip_reason_to_notice_code("corrupt"), "target_corrupt")
        self.assertEqual(skip_reason_to_notice_code("file unreadable"), "target_unreadable")
        self.assertEqual(skip_reason_to_notice_code("blocked by policy"), "target_unreadable")

    def test_build_push_target_update_branches(self):
        preview = PushPreview(
            prepared=None,
            targets=(
                TargetPreview("written", 1, 0, "Ready"),
                TargetPreview("unchanged", 0, 0, "Unchanged"),
                TargetPreview("pending", 2, 1, "Review"),
            ),
            additions=3,
            removals=1,
            warnings=(),
            created_at="t",
            plan_identifier="p",
            targets_to_update=2,
            unchanged=1,
            skipped=("skipped",),
            corrupt=("broken",),
            blocked=(),
        )
        result = PushResult(word_count=1, written=("written",))
        updates = build_push_target_updates(preview, result)
        statuses = {row.name: row.status for row in updates}
        self.assertEqual(statuses["written"], "Updated")
        self.assertEqual(statuses["unchanged"], "Unchanged")
        self.assertEqual(statuses["pending"], "Skipped: not written")
        self.assertIn("Skipped", statuses["skipped"])

    def test_push_planned_actual_missing_actual_row(self):
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
            skipped=(),
            corrupt=(),
            blocked=(),
        )
        lines = format_push_planned_actual_lines(preview, ())
        self.assertIn("Skipped", "\n".join(lines))

    def test_operation_report_notice_branches(self):
        report = OperationReport(
            operation="push",
            outcome=OperationOutcome.COMPLETED_WITH_WARNINGS,
            title="Push completed with warnings",
            summary="done",
            warnings=(
                "Operation completed, but its history record could not be saved.",
                "jetbrains: Application is running",
            ),
        )
        notices = operation_report_notices(report)
        codes = {notice.code for notice in notices}
        self.assertIn("history_write_failed", codes)
        self.assertIn("application_running", codes)

    def test_format_operation_report_conflict_notice(self):
        report = OperationReport(
            operation="push",
            outcome=OperationOutcome.STOPPED_SAFELY,
            title="Push stopped safely",
            summary="conflict",
            conflict_target="chrome:Default",
        )
        text = format_operation_report_text(report)
        self.assertIn("Preview is stale", text)

    def test_metadata_helpers(self):
        from spell_sync.application.operation_explanations import (
            dictionary_display_name,
            pull_report_metadata_lines,
            push_report_metadata_lines,
            recovery_blocker_notice,
        )

        self.assertEqual(dictionary_display_name("macos-spelling"), "macOS Spelling")
        self.assertEqual(
            push_report_metadata_lines(
                PushPreview(
                    prepared=None,
                    targets=(),
                    additions=0,
                    removals=0,
                    warnings=(),
                    created_at="t",
                    plan_identifier="p",
                    targets_to_update=0,
                    unchanged=0,
                    skipped=(),
                    corrupt=(),
                    blocked=(),
                ),
                plan_verified=True,
                snapshots_cleaned=True,
            ),
            ("Preview created: t", "Plan verified", "Recovery snapshots cleaned"),
        )
        self.assertEqual(
            pull_report_metadata_lines(
                PullPreview(
                    wordlist_path="/tmp/w.txt",
                    additions=0,
                    before_count=0,
                    after_count=0,
                    sources_used=(),
                    sources_skipped=(),
                    source_rows=(),
                    warnings=(),
                    created_at="t",
                    plan_identifier="p",
                    merged_words=(),
                )
            ),
            ("Preview created: t",),
        )
        self.assertEqual(
            recovery_blocker_notice(status_value="corrupt_journal", detail="bad").code,
            "corrupt_journal",
        )
        self.assertEqual(
            recovery_blocker_notice(status_value="pending_recovery").code,
            "pending_recovery",
        )
        self.assertEqual(
            recovery_blocker_notice(status_value="recoverable").code,
            "pending_recovery",
        )
        self.assertEqual(
            pull_report_metadata_lines(
                PullPreview(
                    wordlist_path="/tmp/w.txt",
                    additions=0,
                    before_count=0,
                    after_count=0,
                    sources_used=(),
                    sources_skipped=(),
                    source_rows=(),
                    warnings=(),
                    created_at="",
                    plan_identifier="p",
                    merged_words=(),
                )
            ),
            (),
        )
        self.assertEqual(dictionary_display_name("win-spelling"), "Windows Spelling")
        self.assertEqual(dictionary_display_name("plain"), "plain")

    def test_notice_technical_without_detail(self):
        notice = build_notice("operation_locked", detail="pid 123")
        self.assertIsNone(notice.technical_detail)
        self.assertEqual(format_notice_technical(notice), "reason=operation_locked")

    def test_target_ids_from_detail_edges(self):
        issue = DashboardIssue(
            code="corrupt_target",
            severity=DashboardSeverity.BLOCKED,
            title="Corrupt",
            detail="no colon detail",
        )
        notice = dashboard_issue_to_notice(issue)
        self.assertEqual(notice.technical_detail, "reason=target_corrupt")
        empty_targets = DashboardIssue(
            code="skipped_unreadable",
            severity=DashboardSeverity.WARNING,
            title="Unreadable",
            detail="Affected targets: .",
        )
        empty_notice = dashboard_issue_to_notice(empty_targets)
        self.assertEqual(empty_notice.technical_detail, "reason=target_unreadable")
        platform_targets = DashboardIssue(
            code="skipped_unreadable",
            severity=DashboardSeverity.WARNING,
            title="Unreadable",
            detail="Affected targets: macos-spelling, win-spelling.",
        )
        platform_notice = dashboard_issue_to_notice(platform_targets)
        self.assertIn("target=macos_spelling,win_spelling", platform_notice.technical_detail or "")
        plain_target = DashboardIssue(
            code="skipped_unreadable",
            severity=DashboardSeverity.WARNING,
            title="Unreadable",
            detail="Affected targets: chrome.",
        )
        plain_notice = dashboard_issue_to_notice(plain_target)
        self.assertIn("target=chrome", plain_notice.technical_detail or "")

    def test_planned_target_updates_include_corrupt(self):
        preview = PushPreview(
            prepared=None,
            targets=(),
            additions=0,
            removals=0,
            warnings=(),
            created_at="t",
            plan_identifier="p",
            targets_to_update=0,
            unchanged=0,
            skipped=(),
            corrupt=("broken",),
            blocked=(),
        )
        rows = build_push_target_updates(preview, None)
        self.assertEqual(rows[0].status, "Corrupt")


_STALE_CONFIG_MESSAGE = (
    "Configuration update stopped safely\n"
    "spell-sync.toml changed after the preview was created.\n"
    "The newer file was not overwritten."
)


if __name__ == "__main__":
    unittest.main()
