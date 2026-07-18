"""Tests for the UI-neutral application facade."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from spell_sync.application import SpellSyncService
from spell_sync.application.events import OperationEvent
from spell_sync.application.reports import DashboardSeverity, StatusSnapshot
from spell_sync.cli_options import CliOptions
from spell_sync.exit_codes import ExitCode
from spell_sync.push_journal import JournalLoadResult, JournalLoadStatus
from spell_sync.push_prepared import PreparedPush
from spell_sync.settings import ConfigStatus
from spell_sync.sync_models import DictionaryDiff, PushResult
from spell_sync.sync_run import SyncRun


def _pull_scope(wordlist: str = "/tmp/w.txt"):
    ctx = MagicMock()
    ctx.wordlist_str = wordlist
    ctx.wordlist_file = Path(wordlist)
    validated = MagicMock()
    validated.context = ctx
    return validated


class TestSpellSyncService(unittest.TestCase):
    def test_load_status_delegates_to_sync_run(self):
        service = SpellSyncService()
        diff = DictionaryDiff(
            name="demo",
            target_count=2,
            local_count=1,
            to_add=1,
            to_remove=0,
        )
        run = MagicMock()
        run.check_wordlist.return_value = None
        run.load_wordlist.return_value = {"alpha", "beta"}
        run.status_diffs.return_value = [diff]
        run.skipped_unreadable_dictionary_names.return_value = ()
        run.skipped_corrupt_dictionary_names.return_value = ()
        run.destructive_push_risk.return_value = None

        with patch("spell_sync.command_helpers.sync_run_for", return_value=run):
            snapshot = service.load_status(CliOptions())

        self.assertEqual(snapshot.wordlist_count, 2)
        self.assertEqual(snapshot.diffs, (diff,))

    def test_push_event_order_is_deterministic(self):
        service = SpellSyncService()
        prepared = MagicMock(spec=PreparedPush)
        prepared.max_removals.return_value = 0
        run = MagicMock()
        run.prepare_push_operation.return_value = prepared
        run.push_from_wordlist.return_value = PushResult(word_count=1, written=("demo",))

        events: list[OperationEvent] = []

        with patch("spell_sync.application.service.plan_fingerprint_conflict", return_value=None):
            service.prepare_push(run, CliOptions(), event_sink=events.append)
            service.execute_push(run, prepared, dry_run=False, event_sink=events.append)

        stages = [event.stage for event in events]
        self.assertEqual(
            stages,
            ["building_plan", "verifying_plan", "creating_snapshots", "completed"],
        )

    def test_execute_push_uses_prepared_without_replan(self):
        service = SpellSyncService()
        prepared = MagicMock(spec=PreparedPush)
        run = MagicMock()
        run.push_from_wordlist.return_value = PushResult(word_count=1, written=("demo",))

        with patch("spell_sync.application.service.plan_fingerprint_conflict", return_value=None):
            result = service.execute_push(run, prepared, dry_run=False)

        run.prepare_push_operation.assert_not_called()
        run.push_from_wordlist.assert_called_once_with(prepared=prepared)
        self.assertIsInstance(result, PushResult)

    def test_fingerprint_conflict_returns_abort_without_execute(self):
        service = SpellSyncService()
        prepared = MagicMock(spec=PreparedPush)
        run = MagicMock()

        with patch(
            "spell_sync.application.service.plan_fingerprint_conflict",
            return_value="cursor",
        ):
            result = service.execute_push(run, prepared, dry_run=False)

        run.push_from_wordlist.assert_not_called()
        self.assertEqual(result, ExitCode.PUSH_ABORT)

    def test_application_modules_do_not_import_textual(self):
        import importlib
        import pkgutil

        import spell_sync.application as application_pkg

        for module_info in pkgutil.walk_packages(
            application_pkg.__path__,
            application_pkg.__name__ + ".",
        ):
            module = importlib.import_module(module_info.name)
            source_path = getattr(module, "__file__", "") or ""
            if source_path.endswith(".py"):
                text = Path(source_path).read_text(encoding="utf-8")
                self.assertNotIn("textual", text.lower())

    def test_cmd_push_passes_same_prepared_to_execute_without_reprepare(self):
        import spell_sync.commands as commands_mod

        prepared = MagicMock(spec=PreparedPush)
        prepared.max_removals.return_value = 0
        run = MagicMock()
        service = MagicMock()
        service.prepare_push.return_value = prepared
        service.execute_push.return_value = PushResult(word_count=1, written=("demo",))

        with patch.object(commands_mod, "_SERVICE", service):
            with patch.object(commands_mod, "sync_run_for", return_value=run):
                with patch.object(commands_mod, "mutating_command_scope") as scope_cm:
                    scope_cm.return_value.__enter__.return_value = MagicMock()
                    scope_cm.return_value.__exit__.return_value = False
                    code = commands_mod._cmd_push_locked(CliOptions(yes=True, dry_run=True))

        self.assertEqual(code, 0)
        service.prepare_push.assert_called_once_with(run, CliOptions(yes=True, dry_run=True))
        service.execute_push.assert_called_once()
        execute_args, execute_kwargs = service.execute_push.call_args
        self.assertIs(execute_args[0], run)
        self.assertIs(execute_args[1], prepared)
        self.assertTrue(execute_kwargs["dry_run"])
        service.run_push.assert_not_called()

    def test_load_dashboard_composes_runtime_and_status(self):
        service = SpellSyncService()
        snapshot = StatusSnapshot(
            wordlist_count=2,
            diffs=(),
            skipped_unreadable=(),
            skipped_corrupt=(),
        )
        validated = MagicMock()
        validated.config_result.status = ConfigStatus.VALID
        validated.config_result.diagnostics = ()
        validated.context.dictionaries = [MagicMock(), MagicMock(), MagicMock()]
        validated.context.wordlist_file = Path("/tmp/w.txt")
        validated.context.project_dir = Path("/tmp")
        validated.journal_result = JournalLoadResult(JournalLoadStatus.ABSENT, None)

        with patch("spell_sync.paths.resolve_wordlist_path", return_value=Path("/tmp/w.txt")):
            with patch(
                "spell_sync.application.service.build_validated_runtime",
                return_value=validated,
            ):
                with patch(
                    "spell_sync.application.service.read_active_operation_lock",
                    return_value=None,
                ):
                    with patch.object(service, "load_status", return_value=snapshot) as load_status:
                        state = service.load_dashboard(CliOptions(wordlist="/tmp/w.txt"))

        load_status.assert_called_once()
        self.assertEqual(state.wordlist_path, "/tmp/w.txt")
        self.assertTrue(state.config_valid)
        self.assertEqual(state.overall_severity, DashboardSeverity.READY)
        self.assertEqual(state.targets_detected, 3)
        self.assertIs(state.snapshot, snapshot)

    def test_load_push_preview_returns_prepared_push(self):
        service = SpellSyncService()
        prepared = MagicMock(spec=PreparedPush)
        prepared.targets = ()
        prepared.skipped_unreadable = ()
        prepared.skipped_corrupt = ()
        prepared.skipped_blocked = ()
        prepared.ctx = MagicMock()
        prepared.ctx.wordlist_str = "/tmp/w.txt"
        prepared.wordlist_rendered = None
        run = MagicMock()
        run.check_wordlist.return_value = None

        with patch("spell_sync.command_helpers.sync_run_for", return_value=run):
            with patch.object(service, "prepare_push", return_value=prepared):
                preview = service.load_push_preview(CliOptions())

        self.assertIs(preview.prepared, prepared)
        self.assertIsNone(preview.wordlist_error)
        self.assertIsNone(preview.prepare_error)

    def test_load_push_preview_wordlist_error_short_circuits(self):
        service = SpellSyncService()
        run = MagicMock()
        run.check_wordlist.return_value = ExitCode.PUSH_ABORT

        with patch("spell_sync.command_helpers.sync_run_for", return_value=run):
            preview = service.load_push_preview(CliOptions())

        self.assertEqual(preview.wordlist_error, ExitCode.PUSH_ABORT)
        self.assertIsNone(preview.prepared)
        run.prepare_push_operation.assert_not_called()

    def test_load_push_preview_prepare_error(self):
        service = SpellSyncService()
        run = MagicMock()
        run.check_wordlist.return_value = None

        with patch("spell_sync.command_helpers.sync_run_for", return_value=run):
            with patch.object(service, "prepare_push", return_value=ExitCode.PUSH_ABORT):
                preview = service.load_push_preview(CliOptions())

        self.assertEqual(preview.prepare_error, ExitCode.PUSH_ABORT)
        self.assertIsNone(preview.prepared)

    def test_load_status_detail_delegates_to_builder(self):
        service = SpellSyncService()
        run = MagicMock()
        detail = MagicMock()

        with patch("spell_sync.command_helpers.sync_run_for", return_value=run):
            with patch(
                "spell_sync.application.service.build_status_detail_snapshot",
                return_value=detail,
            ) as builder:
                result = service.load_status_detail(CliOptions())

        builder.assert_called_once_with(run)
        self.assertIs(result, detail)

    def test_load_doctor_wraps_report(self):
        service = SpellSyncService()
        report = MagicMock()
        snapshot = MagicMock()

        with patch("spell_sync.command_helpers.sync_run_for", return_value=MagicMock()):
            with patch("spell_sync.application.service.build_doctor_report", return_value=report):
                with patch(
                    "spell_sync.application.service.build_doctor_snapshot",
                    return_value=snapshot,
                ) as builder:
                    result = service.load_doctor(CliOptions())

        builder.assert_called_once_with(report)
        self.assertIs(result, snapshot)

    def test_load_doctor_returns_controlled_error(self):
        service = SpellSyncService()
        with patch(
            "spell_sync.application.service.command_helpers.sync_run_for",
            side_effect=RuntimeError("boom"),
        ):
            snapshot = service.load_doctor(CliOptions())
        self.assertEqual(snapshot.load_error, "Doctor report could not be loaded.")

    def test_run_push_wraps_execute_push_result(self):
        service = SpellSyncService()
        prepared = MagicMock(spec=PreparedPush)
        run = MagicMock()
        push_result = PushResult(word_count=1, written=("demo",))

        with patch.object(service, "execute_push", return_value=push_result) as execute_push:
            execution = service.run_push(
                run,
                CliOptions(),
                prepared,
                dry_run=False,
                event_sink=[],
            )

        execute_push.assert_called_once()
        self.assertIs(execution.prepared, prepared)
        self.assertIs(execution.result, push_result)

    def test_prepare_pull_delegates_to_builder(self):
        from spell_sync.application.reports import PullPreview

        service = SpellSyncService()
        run = MagicMock()
        preview = MagicMock(spec=PullPreview)
        with patch("spell_sync.command_helpers.sync_run_for", return_value=run):
            with patch(
                "spell_sync.application.service.build_pull_preview",
                return_value=preview,
            ) as builder:
                result = service.prepare_pull(CliOptions())
        builder.assert_called_once_with(run)
        self.assertIs(result, preview)

    def test_execute_pull_plan_mismatch_and_write(self):
        from spell_sync.application.reports import OperationOutcome, PullPreview

        service = SpellSyncService()
        preview = PullPreview(
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
        bad = service.execute_pull(CliOptions(), preview, confirmed_plan_id="other")
        self.assertEqual(bad.outcome, OperationOutcome.FAILED)

        events: list = []
        with patch(
            "spell_sync.application.service.command_helpers.mutating_command_scope"
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
                    return_value=(preview.before_count, preview.after_count),
                ) as execute:
                    ok = service.execute_pull(
                        CliOptions(),
                        preview,
                        confirmed_plan_id="p1",
                        event_sink=events.append,
                    )
        execute.assert_called_once()
        self.assertEqual(ok.outcome, OperationOutcome.COMPLETED)
        self.assertTrue(any(event.stage == "completed" for event in events))

    def test_execute_push_preview_conflict_and_success(self):
        from spell_sync.application.reports import OperationOutcome, PushPreview

        service = SpellSyncService()
        prepared = MagicMock(spec=PreparedPush)
        prepared.targets = ()
        prepared.wordlist_needs_write = False
        prepared.ctx = MagicMock(wordlist_str="/tmp/w.txt")
        preview = PushPreview(
            prepared=prepared,
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
        with patch(
            "spell_sync.application.service.command_helpers.mutating_command_scope"
        ) as scope:
            scope.return_value.__enter__.return_value = MagicMock()
            scope.return_value.__exit__.return_value = False
            with patch(
                "spell_sync.application.service.plan_fingerprint_conflict",
                return_value="chrome",
            ):
                conflict = service.execute_push_preview(
                    CliOptions(),
                    preview,
                    confirmed_plan_id="p1",
                )
        self.assertEqual(conflict.outcome, OperationOutcome.STOPPED_SAFELY)
        self.assertEqual(conflict.conflict_target, "chrome")

        with patch(
            "spell_sync.application.service.command_helpers.mutating_command_scope"
        ) as scope:
            scope.return_value.__enter__.return_value = MagicMock()
            scope.return_value.__exit__.return_value = False
            with patch(
                "spell_sync.application.service.plan_fingerprint_conflict",
                return_value=None,
            ):
                with patch(
                    "spell_sync.application.service.execute_prepared_push",
                    return_value=PushResult(word_count=1, written=("demo",)),
                ):
                    ok = service.execute_push_preview(
                        CliOptions(),
                        preview,
                        confirmed_plan_id="p1",
                    )
        self.assertEqual(ok.outcome, OperationOutcome.COMPLETED)
        self.assertIs(ok.prepared, prepared)

    def test_status_cli_uses_service_snapshot(self):
        import spell_sync.commands as commands_mod

        service = SpellSyncService()
        with patch.object(
            commands_mod._SERVICE,
            "load_status",
            wraps=service.load_status,
        ) as load_status:
            with patch("spell_sync.command_helpers.sync_run_for") as sync_run_for:
                run = MagicMock()
                run.check_wordlist.return_value = None
                run.load_wordlist.return_value = {"alpha"}
                run.status_diffs.return_value = []
                run.skipped_unreadable_dictionary_names.return_value = ()
                run.skipped_corrupt_dictionary_names.return_value = ()
                run.destructive_push_risk.return_value = None
                sync_run_for.return_value = run
                code = commands_mod.cmd_status(CliOptions())
        load_status.assert_called_once()
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
