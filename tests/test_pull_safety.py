"""Pull safety regressions for application facade and CLI/TUI parity."""

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from spell_sync.application.push_pull_preview_builders import build_pull_preview
from spell_sync.application.reports import OperationOutcome
from spell_sync.application.requests import ProjectRef, PullRequest
from spell_sync.application.service import SpellSyncService
from spell_sync.cli_options import CliOptions
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.operation_lock import OperationLocked, OperationLockInfo, lock_path_for_wordlist
from spell_sync.push_journal import (
    journal_path_for_wordlist,
)
from spell_sync.sync_run import SyncRun
from tests.journal_test_utils import write_test_journal
from tests.runtime_helpers import make_sync_run, pull_into_wordlist


def _patch_run_discover(run: SyncRun):
    return patch(
        "spell_sync.application._runtime_factory.discover_dictionaries",
        return_value=run.context.dictionaries,
    )


class TestPullSafety(unittest.TestCase):
    def _project(self, tmp: str) -> tuple[Path, Path, SyncRun, PullRequest, CliOptions]:
        root = Path(tmp)
        wordlist = root / "wordlist.txt"
        dictionary = root / "local.txt"
        wordlist.write_text("alpha\nbeta\n", encoding="utf-8")
        dictionary.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
        (root / "spell-sync.toml").write_text("[dictionaries]\neditors = false\n", encoding="utf-8")
        run = make_sync_run(
            wordlist,
            dictionaries=[Dictionary("custom", str(dictionary), DictionaryFormat.TEXT)],
        )
        opts = CliOptions(wordlist=str(wordlist))
        request = PullRequest(project=ProjectRef(wordlist=wordlist))
        return wordlist, dictionary, run, request, opts

    def test_active_operation_lock_blocks_pull(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, _dictionary, run, request, _opts = self._project(tmp)
            preview = build_pull_preview(run)
            info = OperationLockInfo(99, "2026-01-01T00:00:00+00:00", "push", str(wordlist))
            lock_path = lock_path_for_wordlist(wordlist)
            with patch(
                "spell_sync.mutation_guards.acquire_operation_lock",
                side_effect=OperationLocked(info, lock_path),
            ):
                execution = SpellSyncService().execute_pull(
                    request,
                    preview,
                    confirmed_plan_id=preview.plan_identifier,
                )
            self.assertEqual(execution.outcome, OperationOutcome.FAILED)

    def test_pending_recovery_blocks_pull(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, _dictionary, run, request, _opts = self._project(tmp)
            write_test_journal(wordlist, wordlist_write_started=True)
            preview = build_pull_preview(run)
            execution = SpellSyncService().execute_pull(
                request,
                preview,
                confirmed_plan_id=preview.plan_identifier,
            )
            self.assertEqual(execution.outcome, OperationOutcome.FAILED)

    def test_corrupt_journal_blocks_pull(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, _dictionary, run, request, _opts = self._project(tmp)
            journal_path_for_wordlist(wordlist).write_text("{bad json", encoding="utf-8")
            preview = build_pull_preview(run)
            execution = SpellSyncService().execute_pull(
                request,
                preview,
                confirmed_plan_id=preview.plan_identifier,
            )
            self.assertEqual(execution.outcome, OperationOutcome.FAILED)

    def test_invalid_config_blocks_pull(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, _dictionary, run, request, _opts = self._project(tmp)
            (wordlist.parent / "spell-sync.toml").write_text("[[dictionaries]]\n", encoding="utf-8")
            preview = build_pull_preview(run)
            execution = SpellSyncService().execute_pull(
                request,
                preview,
                confirmed_plan_id=preview.plan_identifier,
            )
            self.assertEqual(execution.outcome, OperationOutcome.FAILED)

    def test_wordlist_changed_after_preview_is_controlled_conflict(self):
        service = SpellSyncService()
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, _dictionary, run, request, _opts = self._project(tmp)
            preview = build_pull_preview(run)
            wordlist.write_text("alpha\nbeta\nchanged\n", encoding="utf-8")
            execution = service.execute_pull(
                request,
                preview,
                confirmed_plan_id=preview.plan_identifier,
            )
            self.assertEqual(execution.outcome, OperationOutcome.STOPPED_SAFELY)
            self.assertIn("changed", execution.message.lower())

    def _capture_pull_write_failure(self, *, change_wordlist: bool):
        """Drive the pull write-failure emit and return its captured technical event.

        ``runtime_identity`` is cleared so the harness reaches the write path instead
        of short-circuiting at the runtime-identity guard.
        """
        from spell_sync.diagnostics.technical_event_model import EventId

        captured = []
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, _dictionary, run, request, _opts = self._project(tmp)
            preview = replace(build_pull_preview(run), runtime_identity=None)
            if change_wordlist:
                wordlist.write_text("alpha\nbeta\nchanged\n", encoding="utf-8")
            with patch(
                "spell_sync.diagnostics.technical_event_log.write_technical_event",
                side_effect=captured.append,
            ):
                with patch.object(
                    SyncRun, "execute_prepared_pull", return_value=ExitCode.PUSH_ABORT
                ):
                    execution = SpellSyncService().execute_pull(
                        request,
                        preview,
                        confirmed_plan_id=preview.plan_identifier,
                    )
        terminal = {EventId.PULL_WORDLIST_CHANGED, EventId.PULL_WRITE_FAILED}
        events = [event for event in captured if event.event_id in terminal]
        self.assertEqual(len(events), 1)
        return execution, events[0]

    def test_pull_write_failure_records_terminal_outcome(self):
        """The write-failure technical event must carry its terminal outcome.

        Regression: the emit passed ``OperationOutcome.<...>.value`` (a string),
        which ``build_technical_event`` cannot map, silently dropping the outcome
        from the technical log.
        """
        from spell_sync.diagnostics.event_metadata import TerminalOutcome

        execution, event = self._capture_pull_write_failure(change_wordlist=False)
        self.assertEqual(execution.outcome, OperationOutcome.FAILED)
        self.assertEqual(event.outcome, TerminalOutcome.FAILED)

    def test_pull_conflict_records_terminal_outcome(self):
        from spell_sync.diagnostics.event_metadata import TerminalOutcome

        execution, event = self._capture_pull_write_failure(change_wordlist=True)
        self.assertEqual(execution.outcome, OperationOutcome.STOPPED_SAFELY)
        self.assertEqual(event.outcome, TerminalOutcome.STOPPED_SAFELY)

    def test_external_wordlist_change_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, _dictionary, run, request, _opts = self._project(tmp)
            preview = build_pull_preview(run)
            wordlist.write_text("alpha\nbeta\nexternal\n", encoding="utf-8")
            SpellSyncService().execute_pull(
                request,
                preview,
                confirmed_plan_id=preview.plan_identifier,
            )
            words = wordlist.read_text(encoding="utf-8")
            self.assertIn("external", words)
            self.assertNotIn("gamma", words)

    def test_write_failure_does_not_report_success(self):
        service = SpellSyncService()
        with tempfile.TemporaryDirectory() as tmp:
            _wordlist, _dictionary, run, request, _opts = self._project(tmp)
            preview = build_pull_preview(run)
            with patch.object(SyncRun, "execute_prepared_pull", return_value=ExitCode.PUSH_ABORT):
                execution = service.execute_pull(
                    request,
                    preview,
                    confirmed_plan_id=preview.plan_identifier,
                )
            self.assertNotEqual(execution.outcome, OperationOutcome.COMPLETED)

    def test_service_routes_through_sync_run_execute_prepared_pull(self):
        service = SpellSyncService()
        with tempfile.TemporaryDirectory() as tmp:
            _wordlist, _dictionary, run, request, _opts = self._project(tmp)
            preview = build_pull_preview(run)
            with _patch_run_discover(run):
                with patch.object(
                    SyncRun,
                    "execute_prepared_pull",
                    return_value=(preview.before_count, preview.after_count),
                ) as execute:
                    execution = service.execute_pull(
                        request,
                        preview,
                        confirmed_plan_id=preview.plan_identifier,
                    )
            execute.assert_called_once()
            self.assertEqual(execution.outcome, OperationOutcome.COMPLETED)

    def test_cli_and_service_share_execute_prepared_pull(self):
        with tempfile.TemporaryDirectory() as tmp:
            _wordlist, _dictionary, run, request, _opts = self._project(tmp)
            preview = build_pull_preview(run)
            expected = (preview.before_count, preview.after_count)
            with _patch_run_discover(run):
                with patch.object(
                    SyncRun,
                    "execute_prepared_pull",
                    return_value=expected,
                ) as execute:
                    service_result = SpellSyncService().execute_pull(
                        request,
                        preview,
                        confirmed_plan_id=preview.plan_identifier,
                    )
            execute.assert_called_once()
            self.assertEqual(service_result.outcome, OperationOutcome.COMPLETED)

    def test_pull_into_wordlist_delegates_to_execute_prepared_pull(self):
        with tempfile.TemporaryDirectory() as tmp:
            _wordlist, _dictionary, run, _request, _opts = self._project(tmp)
            with patch.object(
                SyncRun,
                "execute_prepared_pull",
                return_value=(2, 3),
            ) as execute:
                result = pull_into_wordlist(run)
            execute.assert_called_once()
            self.assertEqual(result, (2, 3))

    def test_pull_events_include_real_stages(self):
        events: list = []
        with tempfile.TemporaryDirectory() as tmp:
            _wordlist, _dictionary, run, request, _opts = self._project(tmp)
            preview = build_pull_preview(run)
            with _patch_run_discover(run):
                SpellSyncService().execute_pull(
                    request,
                    preview,
                    confirmed_plan_id=preview.plan_identifier,
                    event_sink=events.append,
                )
        from spell_sync.application.events import EventId

        event_ids = [event.event_id for event in events]
        self.assertIn(EventId.PULL_VALIDATING, event_ids)
        self.assertIn(EventId.PULL_LOCK_ACQUIRED, event_ids)
        self.assertIn(EventId.PULL_PLAN_VERIFIED, event_ids)
        if preview.source_rows:
            self.assertIn(EventId.PULL_SOURCE_STARTED, event_ids)
        self.assertIn(EventId.PULL_WRITE_STARTED, event_ids)
        self.assertIn(EventId.PULL_COMPLETED, event_ids)

    def test_skipped_corrupt_source_is_completed_with_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            good = root / "good.txt"
            bad = root / "bad.json"
            wordlist.write_text("alpha\n", encoding="utf-8")
            good.write_text("alpha\nbeta\n", encoding="utf-8")
            bad.write_text("{not json", encoding="utf-8")
            (root / "spell-sync.toml").write_text(
                "[dictionaries]\neditors = false\n", encoding="utf-8"
            )
            run = make_sync_run(
                wordlist,
                dictionaries=[
                    Dictionary("good", str(good), DictionaryFormat.TEXT),
                    Dictionary("bad", str(bad), DictionaryFormat.JSON),
                ],
            )
            request = PullRequest(project=ProjectRef(wordlist=wordlist))
            with _patch_run_discover(run):
                preview = build_pull_preview(run)
                self.assertIn("bad", preview.sources_skipped)
                execution = SpellSyncService().execute_pull(
                    request,
                    preview,
                    confirmed_plan_id=preview.plan_identifier,
                )
            self.assertEqual(execution.outcome, OperationOutcome.COMPLETED_WITH_WARNINGS)
            self.assertIn("skipped", execution.message.lower())
            self.assertEqual(wordlist.read_text(encoding="utf-8").splitlines(), ["alpha", "beta"])

    def test_source_changed_after_preview_is_stopped_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist, dictionary, run, request, _opts = self._project(tmp)
            with _patch_run_discover(run):
                preview = build_pull_preview(run)
                dictionary.write_text("alpha\nbeta\ngamma\ndelta\n", encoding="utf-8")
                execution = SpellSyncService().execute_pull(
                    request,
                    preview,
                    confirmed_plan_id=preview.plan_identifier,
                )
            self.assertEqual(execution.outcome, OperationOutcome.STOPPED_SAFELY)
            self.assertEqual(wordlist.read_text(encoding="utf-8"), "alpha\nbeta\n")


if __name__ == "__main__":
    unittest.main()
