"""Targeted tests for remaining uncovered lines."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

from textual.widgets import Button, Input
from textual.worker import WorkerState

from spell_sync.application.builders import build_recovery_preview
from spell_sync.application.reports import (
    DashboardIssue,
    DashboardSeverity,
    OperationOutcome,
    PullPreview,
    RecoveryExecution,
    RecoveryItemPreview,
    RecoveryOutcome,
    RecoveryStatus,
)
from spell_sync.application.requests import ProjectRef, PullRequest, RecoveryRequest
from spell_sync.application.service import SpellSyncService
from spell_sync.cli_options import CliOptions
from spell_sync.exit_codes import ExitCode
from spell_sync.push_journal import (
    JOURNAL_STATE_ROLLBACK_INCOMPLETE,
    JournalLoadResult,
    JournalLoadStatus,
    RecoverResult,
    _plan_recovery_item,
    _snapshot_is_valid,
    plan_recovery_from_journal,
)
from spell_sync.resolved_runtime import ResolvedRuntime
from spell_sync.settings import ConfigLoadResult, ConfigStatus
from spell_sync.tui.app import SpellSyncApp
from spell_sync.tui.controller import TuiController
from spell_sync.tui.screens.operation_screen import OperationScreen
from spell_sync.tui.screens.recovery_confirm_screen import RecoveryConfirmScreen
from spell_sync.tui.screens.recovery_screen import RecoveryScreen
from tests.journal_test_utils import (
    journal_target_from_file,
    write_restore_scenario_journal,
    write_test_journal,
)
from tests.runtime_helpers import make_sync_run
from tests.test_phase4_facade_coverage import _pull_scope
from tests.tui.fake_service import fake_service, sample_recovery_preview
from tests.tui.test_helpers import wait_for_operation_report, wait_for_text


class TestLineCoverageGaps(unittest.TestCase):
    def test_set_setup_storage_strategy_rejects_unknown(self):
        controller = TuiController(fake_service(), CliOptions())
        with self.assertRaisesRegex(ValueError, "unknown storage strategy"):
            controller.set_setup_storage_strategy("not-a-strategy")
        controller.set_setup_storage_strategy("local")
        self.assertEqual(controller.setup_storage_strategy(), "local")

    def test_execute_pull_wordlist_path_mismatch(self):
        service = SpellSyncService()
        preview = PullPreview(
            wordlist_path="/other/w.txt",
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
            "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
        ) as scope:
            scope.return_value.__enter__.return_value = _pull_scope("/tmp/w.txt")
            scope.return_value.__exit__.return_value = False
            result = service.execute_pull(
                PullRequest(project=ProjectRef()), preview, confirmed_plan_id="p1"
            )
        self.assertEqual(result.outcome, OperationOutcome.FAILED)

    def test_execute_prepared_pull_unreadable_wordlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = make_sync_run(Path(tmp) / "missing.txt")
            with patch.object(run, "check_wordlist", return_value=ExitCode.PUSH_ABORT):
                result = run.execute_prepared_pull(
                    merged_words=("a",),
                    before_count=0,
                    after_count=1,
                    wordlist_fingerprint=None,
                )
            self.assertEqual(result, ExitCode.PUSH_ABORT)

    def test_execute_prepared_pull_fingerprint_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            from spell_sync.push_journal import file_content_hash

            stale_fingerprint = file_content_hash(wordlist)
            wordlist.write_text("changed\n", encoding="utf-8")
            run = make_sync_run(wordlist)
            result = run.execute_prepared_pull(
                merged_words=("alpha", "changed"),
                before_count=1,
                after_count=2,
                wordlist_fingerprint=stale_fingerprint,
            )
            self.assertEqual(result, ExitCode.PUSH_ABORT)
            self.assertEqual(wordlist.read_text(encoding="utf-8"), "changed\n")

    def test_recovery_service_remaining_paths(self):
        service = SpellSyncService()
        preview = sample_recovery_preview(
            items=(
                RecoveryItemPreview(
                    name="wordlist",
                    path="/tmp/w.txt",
                    current_state="Post-write",
                    recovery_action="Restore snapshot",
                    status="ready",
                ),
                RecoveryItemPreview(
                    name="created",
                    path="/tmp/created.txt",
                    current_state="Post-write",
                    recovery_action="Remove created file",
                    status="ready",
                    existed_before=False,
                    write_started=True,
                ),
                RecoveryItemPreview(
                    name="vscode",
                    path="/tmp/vscode.txt",
                    current_state="External change",
                    recovery_action="No automatic write",
                    status="conflict",
                ),
            ),
        )
        journal = MagicMock()
        journal.transaction_id = preview.transaction_id
        scope = MagicMock()
        scope.context.wordlist_file = Path("/tmp/w.txt")
        scope.journal_result = JournalLoadResult(JournalLoadStatus.ABSENT, None)
        with patch(
            "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
        ) as mutating:
            mutating.return_value.__enter__.return_value = scope
            mutating.return_value.__exit__.return_value = False
            stale = service.execute_recovery(
                RecoveryRequest(project=ProjectRef()),
                preview,
                confirmed_transaction_id=preview.preview_fingerprint,
            )
        self.assertEqual(stale.outcome, RecoveryOutcome.FAILED)

        scope.journal_result = JournalLoadResult(JournalLoadStatus.VALID_IN_PROGRESS, journal)
        events: list = []
        with patch(
            "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
        ) as mutating:
            mutating.return_value.__enter__.return_value = scope
            mutating.return_value.__exit__.return_value = False
            with patch(
                "spell_sync.application._operation_deps.recover_from_journal",
                return_value=RecoverResult(restored=("wordlist",), skipped=(), failed=()),
            ):
                with patch(
                    "spell_sync.application._operation_deps.cleanup_after_successful_recovery"
                ):
                    executed = service.execute_recovery(
                        RecoveryRequest(project=ProjectRef()),
                        preview,
                        confirmed_transaction_id=preview.preview_fingerprint,
                        event_sink=events.append,
                    )
        self.assertEqual(executed.outcome, RecoveryOutcome.RECOVERED)
        from spell_sync.application.events import EventId

        self.assertTrue(
            any(event.event_id is EventId.RECOVERY_WORDLIST_RESTORE_STARTED for event in events)
        )
        self.assertTrue(
            any(event.event_id is EventId.RECOVERY_TARGET_REMOVE_STARTED for event in events)
        )

        cleanup_preview = sample_recovery_preview(
            status=RecoveryStatus.COMPLETED_CLEANUP_PENDING,
            can_cleanup=True,
        )
        with patch(
            "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
        ) as mutating:
            mutating.return_value.__enter__.return_value = int(ExitCode.PUSH_ABORT)
            mutating.return_value.__exit__.return_value = False
            locked_cleanup = service.execute_recovery_cleanup(
                RecoveryRequest(project=ProjectRef()),
                cleanup_preview,
                confirmed_transaction_id=cleanup_preview.preview_fingerprint,
            )
        self.assertEqual(locked_cleanup.outcome, RecoveryOutcome.FAILED)

        scope.journal_result = JournalLoadResult(JournalLoadStatus.VALID_IN_PROGRESS, journal)
        with patch(
            "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
        ) as mutating:
            mutating.return_value.__enter__.return_value = scope
            mutating.return_value.__exit__.return_value = False
            missing_completed = service.execute_recovery_cleanup(
                RecoveryRequest(project=ProjectRef()),
                cleanup_preview,
                confirmed_transaction_id=cleanup_preview.preview_fingerprint,
            )
        self.assertEqual(missing_completed.outcome, RecoveryOutcome.FAILED)

        self.assertEqual(
            service.execute_recovery_discard(
                RecoveryRequest(project=ProjectRef()),
                sample_recovery_preview(can_discard=True),
                confirmed_transaction_id="wrong",
            ).outcome,
            RecoveryOutcome.FAILED,
        )
        self.assertEqual(
            service.execute_recovery_discard(
                RecoveryRequest(project=ProjectRef()),
                sample_recovery_preview(can_discard=False),
                confirmed_transaction_id=sample_recovery_preview().preview_fingerprint,
            ).outcome,
            RecoveryOutcome.FAILED,
        )
        with patch(
            "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
        ) as mutating:
            mutating.return_value.__enter__.return_value = int(ExitCode.PUSH_ABORT)
            mutating.return_value.__exit__.return_value = False
            locked_discard = service.execute_recovery_discard(
                RecoveryRequest(project=ProjectRef()),
                sample_recovery_preview(can_discard=True),
                confirmed_transaction_id=sample_recovery_preview().preview_fingerprint,
            )
        self.assertEqual(locked_discard.outcome, RecoveryOutcome.FAILED)

        discard_preview = sample_recovery_preview(
            status=RecoveryStatus.RECOVERABLE,
            can_discard=True,
        )
        with patch(
            "spell_sync.application.runtime_resolver.RuntimeResolver.mutation_scope"
        ) as mutating:
            mutating.return_value.__enter__.return_value = MagicMock()
            mutating.return_value.__exit__.return_value = False
            with patch("spell_sync.application._operation_deps.discard_completed_journal"):
                discarded = service.execute_recovery_discard(
                    RecoveryRequest(project=ProjectRef()),
                    discard_preview,
                    confirmed_transaction_id=discard_preview.preview_fingerprint,
                )
        self.assertEqual(discarded.outcome, RecoveryOutcome.DISCARDED)

        report = service.build_recovery_report(
            RecoveryExecution(
                preview=preview,
                result=ExitCode.OK,
                outcome=RecoveryOutcome.RECOVERED,
                message="ok",
            )
        )
        self.assertEqual(report.operation, "recover")

    def test_build_recovery_preview_warning_branches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            dict_path = root / "dict.txt"
            wordlist.write_text("after\n", encoding="utf-8")
            dict_path.write_text("external\n", encoding="utf-8")
            journal = write_test_journal(
                wordlist,
                state=JOURNAL_STATE_ROLLBACK_INCOMPLETE,
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            target = journal_target_from_file(
                "dict",
                dict_path,
                Path(journal.snapshot_dir),
                write_started=True,
                write_completed=True,
                hash_after="deadbeef",
            )
            journal.targets = [target]
            ctx = MagicMock()
            ctx.wordlist_file = wordlist
            validated = ResolvedRuntime(
                context=ctx,
                config_result=ConfigLoadResult(ConfigStatus.VALID, {}, ()),
                journal_result=JournalLoadResult(JournalLoadStatus.VALID_IN_PROGRESS, journal),
                identity=MagicMock(),
            )
            preview = build_recovery_preview(validated)
            self.assertEqual(preview.status, RecoveryStatus.RECOVERY_IN_PROGRESS)
            self.assertTrue(preview.warnings)

            conflict_only = root / "conflict.txt"
            conflict_only.write_text("external\n", encoding="utf-8")
            conflict_journal = write_restore_scenario_journal(wordlist, conflict_only)
            conflict_only.write_text("other\n", encoding="utf-8")
            wordlist.write_text("other-wl\n", encoding="utf-8")
            conflict_validated = replace(
                validated,
                journal_result=JournalLoadResult(
                    JournalLoadStatus.VALID_IN_PROGRESS,
                    conflict_journal,
                ),
            )
            only_conflicts = build_recovery_preview(conflict_validated)
            self.assertEqual(only_conflicts.status, RecoveryStatus.CONFLICTED)
            self.assertIn("external conflict", only_conflicts.warnings[-1].lower())

    def test_build_recovery_preview_mixed_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            dict_path = root / "dict.txt"
            journal = write_restore_scenario_journal(
                wordlist,
                dict_path,
                current_wordlist="new\n",
                backup_wordlist="old\n",
                current_dict="new\n",
                backup_dict="old\n",
            )
            dict_path.write_text("external\n", encoding="utf-8")
            ctx = MagicMock()
            ctx.wordlist_file = wordlist
            validated = ResolvedRuntime(
                context=ctx,
                config_result=ConfigLoadResult(ConfigStatus.VALID, {}, ()),
                journal_result=JournalLoadResult(JournalLoadStatus.VALID_IN_PROGRESS, journal),
                identity=MagicMock(),
            )
            mixed = build_recovery_preview(validated)
            self.assertEqual(mixed.status, RecoveryStatus.CONFLICTED)
            self.assertTrue(mixed.recoverable_count > 0)
            self.assertTrue(mixed.conflict_count > 0)

    def test_build_recovery_preview_snapshot_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wordlist = root / "wordlist.txt"
            dict_path = root / "dict.txt"
            wordlist.write_text("new\n", encoding="utf-8")
            dict_path.write_text("new\n", encoding="utf-8")
            journal = write_test_journal(
                wordlist,
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            journal.targets = [
                journal_target_from_file(
                    "dict",
                    dict_path,
                    Path(journal.snapshot_dir),
                    write_started=True,
                    write_completed=True,
                )
            ]
            Path(journal.targets[0].backup_path).unlink()
            ctx = MagicMock()
            ctx.wordlist_file = wordlist
            validated = ResolvedRuntime(
                context=ctx,
                config_result=ConfigLoadResult(ConfigStatus.VALID, {}, ()),
                journal_result=JournalLoadResult(JournalLoadStatus.VALID_IN_PROGRESS, journal),
                identity=MagicMock(),
            )
            failed = build_recovery_preview(validated)
            self.assertGreater(failed.failure_count, 0)
            self.assertIn("invalid snapshots", failed.warnings[0].lower())

    def test_plan_recovery_item_branches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target.txt"
            backup = root / "backup.snap"
            self.assertFalse(_snapshot_is_valid(None, "abc"))
            backup.write_text("snap\n", encoding="utf-8")
            self.assertTrue(_snapshot_is_valid(backup, None))

            skipped = _plan_recovery_item(
                "idle",
                target,
                backup,
                existed_before=True,
                hash_before="x",
                hash_after="y",
                write_started=False,
                write_completed=False,
            )
            self.assertEqual(skipped.status, "skipped")

            created_missing = _plan_recovery_item(
                "new",
                root / "missing.txt",
                backup,
                existed_before=False,
                hash_before=None,
                hash_after="after",
                write_started=True,
                write_completed=True,
            )
            self.assertEqual(created_missing.status, "skipped")

            target.write_text("created\n", encoding="utf-8")
            created_conflict = _plan_recovery_item(
                "new",
                target,
                backup,
                existed_before=False,
                hash_before=None,
                hash_after="other-hash",
                write_started=True,
                write_completed=True,
            )
            self.assertEqual(created_conflict.status, "conflict")

            remove_ready = _plan_recovery_item(
                "new",
                target,
                backup,
                existed_before=False,
                hash_before=None,
                hash_after=__import__(
                    "spell_sync.push_journal", fromlist=["file_content_hash"]
                ).file_content_hash(target),
                write_started=True,
                write_completed=True,
            )
            self.assertEqual(remove_ready.status, "ready")

            existing = root / "existing.txt"
            existing.write_text("current\n", encoding="utf-8")
            missing_snapshot = _plan_recovery_item(
                "old",
                existing,
                None,
                existed_before=True,
                hash_before="before",
                hash_after="after",
                write_started=True,
                write_completed=True,
            )
            self.assertEqual(missing_snapshot.status, "failed")

            bad_backup = root / "bad.snap"
            bad_backup.write_text("wrong\n", encoding="utf-8")
            invalid_snapshot = _plan_recovery_item(
                "old",
                existing,
                bad_backup,
                existed_before=True,
                hash_before="before",
                hash_after="after",
                write_started=True,
                write_completed=True,
            )
            self.assertEqual(invalid_snapshot.status, "failed")

            good_backup = root / "good.snap"
            good_backup.write_text("before\n", encoding="utf-8")
            hash_before = __import__(
                "spell_sync.push_journal", fromlist=["file_content_hash"]
            ).file_content_hash(good_backup)
            external = _plan_recovery_item(
                "old",
                existing,
                good_backup,
                existed_before=True,
                hash_before=hash_before,
                hash_after="after",
                write_started=True,
                write_completed=True,
            )
            self.assertEqual(external.status, "conflict")

            missing_existing = root / "gone.txt"
            missing_plan = _plan_recovery_item(
                "gone",
                missing_existing,
                good_backup,
                existed_before=True,
                hash_before=hash_before,
                hash_after="after",
                write_started=True,
                write_completed=True,
            )
            self.assertEqual(missing_plan.current_state, "Missing")

            real = root / "real.txt"
            real.write_text("x\n", encoding="utf-8")
            symlink_backup = root / "link.snap"
            symlink_backup.symlink_to(real)
            self.assertFalse(_snapshot_is_valid(symlink_backup, hash_before))

            journal = write_test_journal(
                root / "wordlist.txt",
                targets=[],
                wordlist_write_started=True,
                wordlist_write_completed=True,
            )
            self.assertTrue(plan_recovery_from_journal(journal))


class TestLineCoverageGapsUi(unittest.IsolatedAsyncioTestCase):
    async def test_storage_strategy_ignores_unknown_radio(self):
        from spell_sync.application.product_concepts import STORAGE_STRATEGY_LOCAL
        from spell_sync.tui.screens.setup_welcome_screen import SetupStorageStrategyScreen

        controller = TuiController(fake_service(), CliOptions())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(SetupStorageStrategyScreen(controller))
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, SetupStorageStrategyScreen)
            pressed = MagicMock()
            pressed.id = "storage-unknown"
            screen.on_radio_set_changed(MagicMock(pressed=pressed))
            self.assertEqual(screen._selected, STORAGE_STRATEGY_LOCAL)

    async def test_dashboard_corrupt_journal_banner(self):
        controller = TuiController(
            fake_service(
                severity=DashboardSeverity.BLOCKED,
                issues=(
                    DashboardIssue(
                        code="corrupt_journal",
                        severity=DashboardSeverity.BLOCKED,
                        title="Corrupt journal",
                        detail="bad",
                        suggested_action="Recover",
                    ),
                ),
            ),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            await wait_for_text(pilot, "#blocking-banner", "Corrupt recovery journal")

    async def test_recovery_screen_guards_and_callbacks(self):
        preview = sample_recovery_preview()
        service = fake_service(pending_recovery=True, recovery_preview=preview)
        controller = TuiController(service, ProjectRef())
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(RecoveryScreen(controller))
            await wait_for_text(pilot, "#recovery-content", "Recoverable files")
            screen = app.screen
            assert isinstance(screen, RecoveryScreen)
            screen._preview = None
            screen.action_view_details()
            screen.action_run_recover()
            controller.begin_mutation()
            screen._preview = preview
            screen.action_run_recover()
            screen.action_run_discard()
            controller.end_mutation()
            screen._preview = replace(preview, can_discard=False)
            screen.action_run_discard()
            screen._preview = preview
            service.raise_on_inspect = RuntimeError("boom")
            screen.refresh_preview()
            await pilot.pause(0.2)

    async def test_recovery_confirm_wrong_typed_token(self):
        preview = sample_recovery_preview()
        controller = TuiController(fake_service(), CliOptions())
        controller.set_active_recovery_preview(preview)
        app = SpellSyncApp(controller)
        async with app.run_test(size=(120, 40)) as pilot:
            app.push_screen(RecoveryConfirmScreen(controller, preview, "recover"))
            await wait_for_text(pilot, "#confirm-summary", "Type RECOVER")
            screen = app.screen
            assert isinstance(screen, RecoveryConfirmScreen)
            confirm_input = screen.query_one("#confirm-input", Input)
            confirm_input.value = "NOPE"
            run_btn = screen.query_one("#btn-run", Button)
            run_btn.disabled = False
            screen.on_button_pressed(Button.Pressed(run_btn))
            await pilot.pause()

    async def test_operation_cleanup_and_controller_cleanup(self):
        preview = sample_recovery_preview(
            status=RecoveryStatus.COMPLETED_CLEANUP_PENDING,
            can_cleanup=True,
        )
        service = fake_service(recovery_preview=preview)
        controller = TuiController(service, ProjectRef())
        controller.execute_recovery_cleanup(preview)
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(
                OperationScreen(controller, operation="cleanup", recovery_preview=preview)
            )
            await wait_for_operation_report(pilot, "cleanup")

    async def test_recovery_screen_worker_poll_paths(self):
        preview = sample_recovery_preview(
            snapshot_directory="/tmp/snaps",
            can_discard=True,
        )
        controller = TuiController(
            fake_service(pending_recovery=True, recovery_preview=preview),
            CliOptions(),
        )
        app = SpellSyncApp(controller)
        async with app.run_test(size=(100, 36)) as pilot:
            app.push_screen(RecoveryScreen(controller))
            await wait_for_text(pilot, "#recovery-content", "Recoverable files")
            screen = app.screen
            assert isinstance(screen, RecoveryScreen)

            class ErrorWorker:
                state = WorkerState.ERROR

            screen._worker = ErrorWorker()
            screen._poll_recovery_worker()

            screen._active_token = screen._load_generation

            class SuccessWorker:
                state = WorkerState.SUCCESS
                result = preview

            screen._worker = SuccessWorker()
            screen._poll_recovery_worker()

            details_btn = screen.query_one("#btn-details", Button)
            screen.on_button_pressed(Button.Pressed(details_btn))

            with patch.object(app, "push_screen") as push_screen:
                screen.action_run_recover()
                callback = push_screen.call_args.args[1]
                with patch.object(
                    type(screen),
                    "is_mounted",
                    new_callable=PropertyMock,
                    return_value=False,
                ):
                    callback(True)

            controller.begin_mutation()
            screen.action_run_discard()

            controller.end_mutation()
            screen._starting = False
            with patch.object(app, "push_screen") as push_screen:
                screen.action_run_discard()
                discard_callback = push_screen.call_args.args[1]
                with patch.object(
                    type(screen),
                    "is_mounted",
                    new_callable=PropertyMock,
                    return_value=False,
                ):
                    discard_callback(True)


if __name__ == "__main__":
    unittest.main()
