"""Tests for the UI-neutral application facade."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from spell_sync.application import SpellSyncService
from spell_sync.application.events import OperationEvent
from spell_sync.application.reports import StatusSnapshot
from spell_sync.cli_options import CliOptions
from spell_sync.exit_codes import ExitCode
from spell_sync.push_prepared import PreparedPush
from spell_sync.settings import ConfigStatus
from spell_sync.sync_models import DictionaryDiff, PushResult


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
            ["building_plan", "plan_verified", "creating_snapshots", "completed"],
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
        validated.context.dictionaries = [MagicMock(), MagicMock(), MagicMock()]

        with patch("spell_sync.paths.resolve_wordlist_path", return_value=Path("/tmp/w.txt")):
            with patch(
                "spell_sync.validated_runtime.build_validated_runtime",
                return_value=validated,
            ):
                with patch.object(service, "load_status", return_value=snapshot) as load_status:
                    state = service.load_dashboard(CliOptions(wordlist="/tmp/w.txt"))

        load_status.assert_called_once()
        self.assertEqual(state.wordlist_path, "/tmp/w.txt")
        self.assertTrue(state.config_valid)
        self.assertEqual(state.config_status, "valid")
        self.assertEqual(state.targets_detected, 3)
        self.assertIs(state.snapshot, snapshot)

    def test_load_push_preview_delegates_to_sync_run(self):
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
        run.status_diffs.return_value = [diff]
        run.plan_push.return_value = PushResult(word_count=1, written=("demo",))

        with patch("spell_sync.command_helpers.sync_run_for", return_value=run):
            with patch("spell_sync.command_helpers.push_skip_running_app_dicts", return_value=()):
                preview = service.load_push_preview(CliOptions())

        self.assertEqual(preview.diffs, (diff,))
        self.assertIsInstance(preview.plan_result, PushResult)
        self.assertIsNone(preview.wordlist_error)

    def test_load_push_preview_wordlist_error_short_circuits(self):
        service = SpellSyncService()
        run = MagicMock()
        run.check_wordlist.return_value = ExitCode.PUSH_ABORT

        with patch("spell_sync.command_helpers.sync_run_for", return_value=run):
            preview = service.load_push_preview(CliOptions())

        self.assertEqual(preview.wordlist_error, ExitCode.PUSH_ABORT)
        self.assertEqual(preview.plan_result, ExitCode.PUSH_ABORT)
        run.plan_push.assert_not_called()

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
