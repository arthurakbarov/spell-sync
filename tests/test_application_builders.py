"""Tests for application snapshot builders."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from spell_sync.application.builders import (
    _max_severity,
    build_dashboard_issues,
    build_dashboard_state,
    build_doctor_snapshot,
    build_push_preview,
    build_status_detail_snapshot,
)
from spell_sync.application.reports import DashboardSeverity, StatusSnapshot
from spell_sync.exit_codes import ExitCode
from spell_sync.health.types import DoctorCheck, DoctorReport
from spell_sync.operation_lock import OperationLockInfo
from spell_sync.push_journal import JournalLoadResult, JournalLoadStatus
from spell_sync.settings import ConfigLoadResult, ConfigStatus


class TestDashboardBuilders(unittest.TestCase):
    def _validated(self, **kwargs):
        validated = MagicMock()
        validated.config_result = kwargs.get(
            "config_result",
            ConfigLoadResult(ConfigStatus.VALID, {}, ()),
        )
        validated.journal_result = kwargs.get(
            "journal_result",
            JournalLoadResult(JournalLoadStatus.ABSENT, None),
        )
        validated.context.dictionaries = kwargs.get("dictionaries", [MagicMock()])
        validated.context.wordlist_file = Path("/tmp/w.txt")
        validated.context.project_dir = Path("/tmp")
        return validated

    def test_max_severity_ready_only(self):
        self.assertEqual(_max_severity(DashboardSeverity.READY), DashboardSeverity.READY)

    def test_build_dashboard_warning_severity(self):
        snapshot = StatusSnapshot(
            wordlist_count=0,
            diffs=(),
            skipped_unreadable=(),
            skipped_corrupt=(),
            empty_wordlist=True,
        )
        validated = self._validated()
        issues = build_dashboard_issues(validated, snapshot, lock_info=None)
        self.assertTrue(any(issue.severity is DashboardSeverity.WARNING for issue in issues))
        state = build_dashboard_state(validated, snapshot, lock_info=None)
        self.assertEqual(state.overall_severity, DashboardSeverity.WARNING)

    def test_build_status_detail_with_dictionary_row(self):
        import tempfile

        from spell_sync.dictionaries import Dictionary, DictionaryFormat

        with tempfile.TemporaryDirectory() as d:
            dict_path = Path(d) / "chrome.txt"
            dict_path.write_text("alpha\n", encoding="utf-8")
            dictionary = Dictionary("chrome", str(dict_path), DictionaryFormat.TEXT)
            run = MagicMock()
            run.wordlist_str = str(Path(d) / "wordlist.txt")
            run.context.project_dir = Path(d)
            run.context.config_paths = (Path(d) / "spell-sync.toml",)
            run.check_wordlist.return_value = None
            run.load_wordlist.return_value = {"alpha"}
            run.status_diffs.return_value = []
            run.skipped_unreadable_dictionary_names.return_value = ()
            run.skipped_corrupt_dictionary_names.return_value = ()
            run.destructive_push_risk.return_value = None
            run.dictionaries = [dictionary]

            detail = build_status_detail_snapshot(run)
            self.assertEqual(detail.targets[0].name, "chrome")

    def test_build_push_preview_ready_and_unchanged(self):
        planned = MagicMock()
        planned.dictionary.name = "demo"
        planned.additions = frozenset({"only-add"})
        planned.removals = frozenset()
        target = MagicMock()
        target.planned = planned
        prepared = MagicMock()
        prepared.targets = (target,)
        prepared.skipped_unreadable = ()
        prepared.skipped_corrupt = ()
        prepared.skipped_blocked = ()
        prepared.ctx.wordlist_str = "/tmp/w.txt"
        prepared.wordlist_rendered = MagicMock(sha256="abcd1234efgh5678")
        preview = build_push_preview(prepared)
        self.assertEqual(preview.targets[0].status, "Ready")

        planned2 = MagicMock()
        planned2.dictionary.name = "same"
        planned2.additions = frozenset()
        planned2.removals = frozenset()
        target2 = MagicMock()
        target2.planned = planned2
        prepared2 = MagicMock()
        prepared2.targets = (target2,)
        prepared2.skipped_unreadable = ()
        prepared2.skipped_corrupt = ()
        prepared2.skipped_blocked = ()
        prepared2.ctx.wordlist_str = "/tmp/w.txt"
        prepared2.wordlist_rendered = None
        unchanged = build_push_preview(prepared2)
        self.assertEqual(unchanged.targets[0].status, "Unchanged")

    def test_build_status_detail_wordlist_error_skips_load(self):
        run = MagicMock()
        run.wordlist_str = "/tmp/w.txt"
        run.context.project_dir = Path("/tmp")
        run.context.config_paths = ()
        run.check_wordlist.return_value = ExitCode.PUSH_ABORT
        run.load_wordlist.side_effect = AssertionError("must not load wordlist")
        run.status_diffs.return_value = []
        run.skipped_unreadable_dictionary_names.return_value = ()
        run.skipped_corrupt_dictionary_names.return_value = ()
        run.destructive_push_risk.return_value = None
        run.dictionaries = []

        detail = build_status_detail_snapshot(run)
        self.assertEqual(detail.wordlist_count, 0)
        self.assertEqual(detail.wordlist_error, ExitCode.PUSH_ABORT)

    def test_build_push_preview_plan_identifier_oserror(self):
        planned = MagicMock()
        planned.dictionary.name = "chrome"
        planned.additions = frozenset({"a"})
        planned.removals = frozenset()
        target = MagicMock()
        target.planned = planned
        prepared = MagicMock()
        prepared.targets = (target,)
        prepared.skipped_unreadable = ()
        prepared.skipped_corrupt = ()
        prepared.skipped_blocked = ()
        prepared.ctx.wordlist_str = "/tmp/w.txt"
        prepared.wordlist_rendered = None
        with patch(
            "spell_sync.application.builders.file_content_hash",
            side_effect=OSError("denied"),
        ):
            preview = build_push_preview(prepared)
        self.assertEqual(preview.plan_identifier, "1targets")

    def test_build_dashboard_issues_blocked_states(self):
        snapshot = StatusSnapshot(
            wordlist_count=0,
            diffs=(),
            skipped_unreadable=("offline",),
            skipped_corrupt=("broken",),
            wordlist_error=ExitCode.PUSH_ABORT,
            empty_wordlist=True,
            destructive_risk="risk",
        )
        validated = self._validated(
            config_result=ConfigLoadResult(ConfigStatus.SYNTAX_ERROR, None, ()),
            journal_result=JournalLoadResult(
                JournalLoadStatus.VALID_IN_PROGRESS,
                MagicMock(),
            ),
        )
        lock = OperationLockInfo(1, "now", "push", "/tmp/w.txt")
        issues = build_dashboard_issues(validated, snapshot, lock_info=lock)
        codes = {issue.code for issue in issues}
        self.assertIn("invalid_config", codes)
        self.assertIn("pending_recovery", codes)
        self.assertIn("operation_lock", codes)
        self.assertIn("corrupt_target", codes)
        self.assertIn("unreadable_wordlist", codes)

    def test_build_dashboard_state_overall_blocked(self):
        snapshot = StatusSnapshot(
            wordlist_count=0,
            diffs=(),
            skipped_unreadable=(),
            skipped_corrupt=("broken",),
            wordlist_error=ExitCode.PUSH_ABORT,
        )
        validated = self._validated(
            journal_result=JournalLoadResult(JournalLoadStatus.CORRUPT, None, detail="bad"),
        )
        state = build_dashboard_state(validated, snapshot, lock_info=None)
        self.assertEqual(state.overall_severity, DashboardSeverity.BLOCKED)
        self.assertTrue(state.pending_recovery is False)


class TestStatusAndPreviewBuilders(unittest.TestCase):
    def test_build_status_detail_snapshot(self):
        run = MagicMock()
        run.wordlist_str = "/tmp/w.txt"
        run.context.project_dir = Path("/tmp")
        run.context.config_paths = (Path("/tmp/spell-sync.toml"),)
        run.check_wordlist.return_value = None
        run.load_wordlist.return_value = {"a", "b"}
        run.status_diffs.return_value = []
        run.skipped_unreadable_dictionary_names.return_value = ("offline",)
        run.skipped_corrupt_dictionary_names.return_value = ("broken",)
        run.destructive_push_risk.return_value = "risk"
        run.dictionaries = []

        detail = build_status_detail_snapshot(run)
        self.assertEqual(detail.wordlist_count, 2)
        self.assertEqual(detail.skipped_unreadable, ("offline",))

    def test_build_push_preview_with_prepared(self):
        planned = MagicMock()
        planned.dictionary.name = "chrome"
        planned.additions = frozenset({"a"})
        planned.removals = frozenset({"b"})
        target = MagicMock()
        target.planned = planned
        prepared = MagicMock()
        prepared.targets = (target,)
        prepared.skipped_unreadable = ("offline",)
        prepared.skipped_corrupt = ("broken",)
        prepared.skipped_blocked = ("blocked",)
        prepared.ctx.wordlist_str = "/tmp/w.txt"
        prepared.wordlist_rendered = None
        with patch(
            "spell_sync.application.builders.file_content_hash",
            return_value="deadbeef",
        ):
            preview = build_push_preview(prepared)
        self.assertIs(preview.prepared, prepared)
        self.assertEqual(preview.additions, 1)
        self.assertEqual(preview.removals, 1)

    def test_build_push_preview_errors(self):
        blocked = build_push_preview(None, prepare_error=ExitCode.PUSH_ABORT)
        self.assertIsNone(blocked.prepared)
        unreadable = build_push_preview(None, wordlist_error=ExitCode.PUSH_ABORT)
        self.assertIsNone(unreadable.prepared)


class TestDoctorBuilder(unittest.TestCase):
    def test_build_doctor_snapshot_groups_checks(self):
        report = DoctorReport(
            wordlist_path="/tmp/w.txt",
            wordlist_count=1,
            package_version="0.1.0",
            skipped_unreadable=("offline",),
            git_hooks=None,
            cli=MagicMock(
                on_path=True,
                argv=(),
                executable=None,
                pip_script=None,
                path_export=None,
            ),
            actions=(),
            checks=(
                DoctorCheck("error", "config: invalid key"),
                DoctorCheck("warn", "wordlist is empty"),
            ),
            dictionaries_total=2,
            dictionaries_readable=1,
            dictionaries_writable=1,
            max_drift_add=0,
            max_drift_remove=0,
        )
        snapshot = build_doctor_snapshot(report)
        self.assertTrue(snapshot.has_errors)
        self.assertGreaterEqual(len(snapshot.checks), 3)

    def test_build_doctor_snapshot_extra_groups_and_actions(self):
        from spell_sync.health.types import DoctorAction

        report = DoctorReport(
            wordlist_path="/tmp/w.txt",
            wordlist_count=1,
            package_version="0.1.0",
            skipped_unreadable=("offline",),
            git_hooks=None,
            cli=MagicMock(
                on_path=True,
                argv=(),
                executable=None,
                pip_script=None,
                path_export=None,
            ),
            actions=(
                DoctorAction(
                    id="recover",
                    reason="unfinished journal requires recover",
                    command="spell-sync recover",
                ),
            ),
            checks=(
                DoctorCheck("info", "everything nominal"),
                DoctorCheck("error", "unfinished journal requires recover"),
                DoctorCheck("warn", "disk permission problem on config path"),
                DoctorCheck("warn", "firefox dictionary drift detected"),
                DoctorCheck("warn", "operation lock held by another cli"),
            ),
            dictionaries_total=3,
            dictionaries_readable=2,
            dictionaries_writable=0,
            max_drift_add=0,
            max_drift_remove=0,
        )
        snapshot = build_doctor_snapshot(report)
        groups = {check.group for check in snapshot.checks}
        self.assertIn("Transaction state", groups)
        self.assertIn("Dictionaries", groups)
        self.assertIn("Filesystem access", groups)
        self.assertTrue(
            any(check.suggested_action == "spell-sync recover" for check in snapshot.checks)
        )

    def test_build_doctor_snapshot_hint_action_and_passed_level(self):
        from spell_sync.health.types import DoctorAction

        report = DoctorReport(
            wordlist_path="/tmp/w.txt",
            wordlist_count=1,
            package_version="0.1.0",
            skipped_unreadable=(),
            git_hooks=None,
            cli=MagicMock(
                on_path=True,
                argv=(),
                executable=None,
                pip_script=None,
                path_export=None,
            ),
            actions=(
                DoctorAction(
                    id="hint-only",
                    reason="custom hint trigger",
                    hint="follow this hint",
                ),
            ),
            checks=(DoctorCheck("info", "custom hint trigger in message"),),
            dictionaries_total=0,
            dictionaries_readable=0,
            dictionaries_writable=0,
            max_drift_add=0,
            max_drift_remove=0,
        )
        snapshot = build_doctor_snapshot(report)
        self.assertEqual(snapshot.checks[0].level, "passed")
        self.assertEqual(snapshot.checks[0].suggested_action, "follow this hint")


if __name__ == "__main__":
    unittest.main()
