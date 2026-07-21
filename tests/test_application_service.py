"""Tests for the UI-neutral application facade."""

from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

from spell_sync.application import SpellSyncService
from spell_sync.application.events import EventId, PresentedEvent
from spell_sync.application.reports import (
    DashboardSeverity,
    PullPreview,
    PushPreview,
    StatusSnapshot,
)
from spell_sync.application.requests import (
    DoctorRequest,
    ProjectRef,
    PullRequest,
    PushRequest,
    StatusRequest,
)
from spell_sync.application.runtime_resolver import RuntimeResolver
from spell_sync.cli_options import CliOptions
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import write_text_words
from spell_sync.push_journal import JournalLoadResult, JournalLoadStatus
from spell_sync.push_prepared import PreparedPush
from spell_sync.settings import ConfigStatus
from spell_sync.sync_models import DictionaryDiff, PushResult
from spell_sync.sync_run import SyncRun
from tests.runtime_helpers import make_sync_run


@contextmanager
def _patch_mutation_scope(yield_value):
    @contextmanager
    def _fake_scope(_self, _project, _command, **_kwargs):
        yield yield_value

    with patch.object(RuntimeResolver, "mutation_scope", _fake_scope):
        yield


def _pull_scope(wordlist: str = "/tmp/w.txt"):
    ctx = MagicMock()
    ctx.wordlist_str = wordlist
    ctx.wordlist_file = Path(wordlist)
    validated = MagicMock()
    validated.context = ctx
    validated.identity = MagicMock()
    return validated


def _push_scope(runtime_identity):
    scope = MagicMock()
    scope.identity = runtime_identity
    scope.context = MagicMock(settings=MagicMock())
    return scope


def _status(wordlist: str | None = None, *, include_word_diffs: bool = False) -> StatusRequest:
    project = ProjectRef(wordlist=Path(wordlist)) if wordlist else ProjectRef()
    return StatusRequest(project=project, include_word_diffs=include_word_diffs)


def _push(wordlist: str | None = None) -> PushRequest:
    project = ProjectRef(wordlist=Path(wordlist)) if wordlist else ProjectRef()
    return PushRequest(project=project)


def _pull() -> PullRequest:
    return PullRequest(project=ProjectRef())


def _doctor() -> DoctorRequest:
    return DoctorRequest(project=ProjectRef())


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

        with patch.object(RuntimeResolver, "sync_run", return_value=run):
            snapshot = service.load_status(_status())

        self.assertEqual(snapshot.wordlist_count, 2)
        self.assertEqual(snapshot.diffs, (diff,))

    def test_push_event_order_is_deterministic(self):
        service = SpellSyncService()
        prepared = MagicMock(spec=PreparedPush)
        prepared.max_removals.return_value = 0
        run = MagicMock()
        run.prepare_push_operation.return_value = prepared
        run.push_from_wordlist.return_value = PushResult(word_count=1, written=("demo",))

        events: list[PresentedEvent] = []

        with patch(
            "spell_sync.application._operation_deps.plan_fingerprint_conflict", return_value=None
        ):
            service._sync._prepare_push_for_run(run, event_sink=events.append)
            service._sync._execute_push_for_run(
                run,
                prepared,
                dry_run=False,
                event_sink=events.append,
            )

        event_ids = [event.event_id for event in events]
        self.assertEqual(
            event_ids,
            [
                EventId.PUSH_BUILDING_PLAN,
                EventId.PUSH_PLAN_VERIFIED,
                EventId.PUSH_EXECUTION_STARTED,
                EventId.PUSH_COMPLETED,
            ],
        )

    def test_execute_push_for_run_uses_prepared_without_replan(self):
        service = SpellSyncService()
        prepared = MagicMock(spec=PreparedPush)
        run = MagicMock()
        run.push_from_wordlist.return_value = PushResult(word_count=1, written=("demo",))

        with patch(
            "spell_sync.application._operation_deps.plan_fingerprint_conflict", return_value=None
        ):
            result = service._sync._execute_push_for_run(run, prepared, dry_run=False)

        run.prepare_push_operation.assert_not_called()
        run.push_from_wordlist.assert_called_once_with(prepared=prepared)
        self.assertIsInstance(result, PushResult)

    def test_execute_push_for_run_emits_failed_when_push_returns_exit_code(self):
        service = SpellSyncService()
        prepared = MagicMock(spec=PreparedPush)
        run = MagicMock()
        run.push_from_wordlist.return_value = ExitCode.PUSH_ABORT
        events: list[PresentedEvent] = []
        with patch(
            "spell_sync.application._operation_deps.plan_fingerprint_conflict", return_value=None
        ):
            result = service._sync._execute_push_for_run(
                run,
                prepared,
                dry_run=False,
                event_sink=events.append,
            )
        self.assertEqual(result, ExitCode.PUSH_ABORT)
        self.assertTrue(any(event.event_id is EventId.PUSH_FAILED for event in events))

    def test_fingerprint_conflict_returns_abort_without_execute(self):
        service = SpellSyncService()
        prepared = MagicMock(spec=PreparedPush)
        run = MagicMock()

        with patch(
            "spell_sync.application._operation_deps.plan_fingerprint_conflict",
            return_value="cursor",
        ):
            result = service._sync._execute_push_for_run(run, prepared, dry_run=False)

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

    def test_cmd_push_passes_same_preview_to_dry_run_without_reprepare(self):
        import spell_sync.commands as commands_mod
        from spell_sync.application.reports import OperationOutcome, PushExecution, PushPreview

        prepared = MagicMock(spec=PreparedPush)
        prepared.max_removals.return_value = 0
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
        service = MagicMock()
        service.mutating_config_exit_code.return_value = None
        service.load_push_preview.return_value = preview
        service.execute_push_dry_run.return_value = PushExecution(
            prepared=prepared,
            result=PushResult(word_count=1, written=("demo",)),
            outcome=OperationOutcome.COMPLETED,
            message="Push completed.",
            plan_identifier="p1",
            push_preview=preview,
        )
        service.load_status.return_value = StatusSnapshot(
            wordlist_count=1,
            diffs=(),
            skipped_unreadable=(),
            skipped_corrupt=(),
        )

        with patch.object(commands_mod, "_SERVICE", service):
            code = commands_mod.cmd_push(CliOptions(yes=True, dry_run=True))

        self.assertEqual(code, 0)
        service.load_push_preview.assert_called_once()
        service.execute_push_dry_run.assert_called_once()
        execute_args = service.execute_push_dry_run.call_args
        self.assertIs(execute_args[0][1], preview)
        service.execute_push_preview.assert_not_called()
        service.build_push_report.assert_not_called()

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
            with patch.object(
                RuntimeResolver,
                "validated",
                return_value=validated,
            ):
                with patch(
                    "spell_sync.application._operation_deps.read_active_operation_lock",
                    return_value=None,
                ):
                    with patch.object(
                        service._inspection, "load_status", return_value=snapshot
                    ) as load_status:
                        state = service.load_dashboard(_status("/tmp/w.txt"))

        load_status.assert_called_once()
        self.assertEqual(state.wordlist_path, "/tmp/w.txt")
        self.assertTrue(state.config_valid)
        self.assertEqual(state.overall_severity, DashboardSeverity.READY)
        self.assertEqual(state.targets_detected, 3)
        self.assertIs(state.snapshot, snapshot)

    def test_load_dashboard_includes_last_operation_summary(self):
        from datetime import datetime, timezone

        from spell_sync.diagnostics.history_record import OperationHistoryRecord
        from spell_sync.diagnostics.types import OperationHistorySnapshot

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
        validated.context.dictionaries = [MagicMock()]
        validated.context.config = {"dictionaries": {"chrome": True}}
        validated.context.wordlist_file = Path("/tmp/w.txt")
        validated.context.project_dir = Path("/tmp")
        validated.journal_result = JournalLoadResult(JournalLoadStatus.ABSENT, None)
        record = OperationHistoryRecord(
            schema_version=1,
            record_id="r1",
            timestamp=datetime.now(timezone.utc),
            operation="push",
            outcome="completed",
            duration_ms=1,
            updated_targets=2,
        )

        with patch("spell_sync.paths.resolve_wordlist_path", return_value=Path("/tmp/w.txt")):
            with patch.object(
                RuntimeResolver,
                "validated",
                return_value=validated,
            ):
                with patch(
                    "spell_sync.application._operation_deps.read_active_operation_lock",
                    return_value=None,
                ):
                    with patch.object(service._inspection, "load_status", return_value=snapshot):
                        with patch.object(
                            service._diagnostics,
                            "load_operation_history",
                            return_value=OperationHistorySnapshot(records=(record,)),
                        ):
                            state = service.load_dashboard(_status("/tmp/w.txt"))

        self.assertIn("Last: Push", state.last_operation_summary or "")

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

        with patch.object(RuntimeResolver, "sync_run", return_value=run):
            with patch.object(service._sync, "_prepare_push_for_run", return_value=prepared):
                preview = service.load_push_preview(_push())

        self.assertIs(preview.prepared, prepared)
        self.assertIsNone(preview.wordlist_error)
        self.assertIsNone(preview.prepare_error)

    def test_load_push_preview_wordlist_error_short_circuits(self):
        service = SpellSyncService()
        run = MagicMock()
        run.check_wordlist.return_value = ExitCode.PUSH_ABORT

        with patch.object(RuntimeResolver, "sync_run", return_value=run):
            preview = service.load_push_preview(_push())

        self.assertEqual(preview.wordlist_error, ExitCode.PUSH_ABORT)
        self.assertIsNone(preview.prepared)
        run.prepare_push_operation.assert_not_called()

    def test_load_push_preview_prepare_error(self):
        service = SpellSyncService()
        run = MagicMock()
        run.check_wordlist.return_value = None

        with patch.object(RuntimeResolver, "sync_run", return_value=run):
            with patch.object(
                service._sync, "_prepare_push_for_run", return_value=ExitCode.PUSH_ABORT
            ):
                preview = service.load_push_preview(_push())

        self.assertEqual(preview.prepare_error, ExitCode.PUSH_ABORT)
        self.assertIsNone(preview.prepared)

    def test_load_status_detail_delegates_to_builder(self):
        service = SpellSyncService()
        run = MagicMock()
        detail = MagicMock()

        with patch.object(RuntimeResolver, "sync_run", return_value=run):
            with patch(
                "spell_sync.application._operation_deps.build_status_detail_snapshot",
                return_value=detail,
            ) as builder:
                result = service.load_status_detail(_status())

        builder.assert_called_once_with(run)
        self.assertIs(result, detail)

    def test_load_doctor_wraps_report(self):
        service = SpellSyncService()
        report = MagicMock()
        snapshot = MagicMock()

        with patch.object(RuntimeResolver, "sync_run", return_value=MagicMock()):
            with patch(
                "spell_sync.application._operation_deps.build_doctor_report", return_value=report
            ):
                with patch(
                    "spell_sync.application._operation_deps.build_doctor_snapshot",
                    return_value=snapshot,
                ) as builder:
                    result = service.load_doctor(_doctor())

        builder.assert_called_once_with(report)
        self.assertIs(result, snapshot)

    def test_load_doctor_returns_controlled_error(self):
        service = SpellSyncService()
        with patch.object(
            RuntimeResolver,
            "sync_run",
            side_effect=RuntimeError("boom"),
        ):
            snapshot = service.load_doctor(_doctor())
        self.assertEqual(snapshot.load_error, "Doctor report could not be loaded.")

    def test_prepare_pull_delegates_to_builder(self):
        from spell_sync.application.reports import PullPreview

        service = SpellSyncService()
        run = MagicMock()
        preview = MagicMock(spec=PullPreview)
        with patch.object(RuntimeResolver, "sync_run", return_value=run):
            with patch(
                "spell_sync.application._operation_deps.build_pull_preview",
                return_value=preview,
            ) as builder:
                result = service.prepare_pull(_pull())
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
        bad = service.execute_pull(_pull(), preview, confirmed_plan_id="other")
        self.assertEqual(bad.outcome, OperationOutcome.FAILED)

        events: list = []
        with _patch_mutation_scope(_pull_scope()):
            with patch(
                "spell_sync.application._operation_deps.file_content_hash",
                return_value="abc",
            ):
                with patch.object(
                    SyncRun,
                    "execute_prepared_pull",
                    return_value=(preview.before_count, preview.after_count),
                ) as execute:
                    ok = service.execute_pull(
                        _pull(),
                        preview,
                        confirmed_plan_id="p1",
                        event_sink=events.append,
                    )
        execute.assert_called_once()
        self.assertEqual(ok.outcome, OperationOutcome.COMPLETED)
        self.assertTrue(any(event.event_id is EventId.PULL_COMPLETED for event in events))

    def test_execute_push_preview_conflict_and_success(self):
        from spell_sync.application.reports import OperationOutcome, PushPreview

        service = SpellSyncService()
        prepared = MagicMock(spec=PreparedPush)
        prepared.targets = ()
        prepared.wordlist_needs_write = False
        prepared.ctx = MagicMock(wordlist_str="/tmp/w.txt")
        prepared.runtime_identity = MagicMock()
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
        with _patch_mutation_scope(_push_scope(prepared.runtime_identity)):
            with patch(
                "spell_sync.application._operation_deps.plan_fingerprint_conflict",
                return_value="chrome",
            ):
                conflict = service.execute_push_preview(
                    _push(),
                    preview,
                    confirmed_plan_id="p1",
                )
        self.assertEqual(conflict.outcome, OperationOutcome.STOPPED_SAFELY)
        self.assertEqual(conflict.conflict_target, "chrome")

        with _patch_mutation_scope(_push_scope(prepared.runtime_identity)):
            with patch(
                "spell_sync.application._operation_deps.plan_fingerprint_conflict",
                return_value=None,
            ):
                with patch(
                    "spell_sync.application._operation_deps.execute_prepared_push",
                    return_value=PushResult(word_count=1, written=("demo",)),
                ):
                    ok = service.execute_push_preview(
                        _push(),
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
            with patch.object(RuntimeResolver, "sync_run") as sync_run_for:
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


class TestServiceFacadePaths(unittest.TestCase):
    def test_load_status_wordlist_error(self):
        service = SpellSyncService()
        run = MagicMock()
        run.check_wordlist.return_value = ExitCode.WORDLIST_UNREADABLE
        run.skipped_unreadable_dictionary_names.return_value = ("a",)
        run.skipped_corrupt_dictionary_names.return_value = ()
        with patch.object(RuntimeResolver, "sync_run", return_value=run):
            snapshot = service.load_status(_status("/tmp/w.txt"))
        self.assertEqual(snapshot.wordlist_error, ExitCode.WORDLIST_UNREADABLE)

    def test_load_doctor_targets_and_push_plan(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "dict.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(dict_path, ["stale"], "utf-8", False, quiet=True)
            run = make_sync_run(
                wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            service = SpellSyncService(enable_file_logging=False)
            with patch.object(RuntimeResolver, "sync_run", return_value=run):
                targets = service.load_doctor_targets(
                    DoctorRequest(project=ProjectRef(wordlist=Path(wordlist))),
                )
                self.assertEqual(len(targets.targets), 1)
                removals = service.load_push_removals(
                    PushRequest(project=ProjectRef(wordlist=Path(wordlist))),
                )
                self.assertTrue(removals)
                preview, diffs, result = service.load_push_plan(
                    PushRequest(project=ProjectRef(wordlist=Path(wordlist))),
                    verbose=True,
                )
            self.assertTrue(diffs)
            self.assertIsInstance(result, PushResult)

    def test_execute_push_dry_run_and_pull_execution_error(self):
        service = SpellSyncService(enable_file_logging=False)
        prepared = MagicMock(spec=PreparedPush)
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
        pull_preview = PullPreview(
            wordlist_path="/tmp/w.txt",
            additions=0,
            before_count=0,
            after_count=0,
            sources_used=(),
            sources_skipped=(),
            source_rows=(),
            warnings=(),
            created_at="t",
            plan_identifier="pull",
            merged_words=(),
        )
        failed_pull = service.pull_execution_from_result(pull_preview, ExitCode.PUSH_ABORT)
        self.assertEqual(failed_pull.result, ExitCode.PUSH_ABORT)

        blocked = service.execute_push_dry_run(
            _push(),
            PushPreview(
                prepared=None,
                targets=(),
                additions=0,
                removals=0,
                warnings=(),
                created_at="t",
                plan_identifier="blocked",
                targets_to_update=0,
                unchanged=0,
                skipped=(),
                corrupt=(),
                blocked=(),
                prepare_error=ExitCode.PUSH_ABORT,
            ),
        )
        self.assertEqual(blocked.result, ExitCode.PUSH_ABORT)

        with _patch_mutation_scope(int(ExitCode.PUSH_ABORT)):
            locked = service.execute_push_dry_run(_push(), preview)
        self.assertEqual(locked.result, ExitCode.PUSH_ABORT)

        run = MagicMock()
        with patch.object(
            service._sync, "_execute_push_for_run", return_value=PushResult(1, ("a",), ())
        ):
            execution = service._sync._run_push_for_run(run, prepared, dry_run=True)
        self.assertEqual(execution.result.word_count, 1)

    def test_prepare_pull_add_from_paths(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            missing = Path(d) / "missing.txt"
            service = SpellSyncService(enable_file_logging=False)
            unreadable = make_sync_run(wordlist, dictionaries=[])
            with (
                patch.object(RuntimeResolver, "sync_run", return_value=unreadable),
                patch.object(
                    unreadable,
                    "check_wordlist",
                    return_value=ExitCode.WORDLIST_UNREADABLE,
                ),
            ):
                preview = service.prepare_pull(
                    PullRequest(project=ProjectRef(wordlist=wordlist), add_from=str(missing)),
                )
            self.assertEqual(preview.wordlist_error, ExitCode.WORDLIST_UNREADABLE)
            preview = service.prepare_pull(
                PullRequest(project=ProjectRef(wordlist=wordlist), add_from=str(missing)),
            )
            self.assertEqual(preview.prepare_error, ExitCode.PUSH_ABORT)
            hunspell = Path(d) / "extra.dic"
            hunspell.write_text("beta\n", encoding="utf-8")
            preview = service.prepare_pull(
                PullRequest(project=ProjectRef(wordlist=wordlist), add_from=str(hunspell)),
            )
            self.assertGreater(preview.after_count, preview.before_count)

    def test_load_push_plan_blocked_preview(self):
        service = SpellSyncService(enable_file_logging=False)
        run = MagicMock()
        run.status_diffs.return_value = []
        blocked = PushPreview(
            prepared=None,
            targets=(),
            additions=0,
            removals=0,
            warnings=(),
            created_at="t",
            plan_identifier="blocked",
            targets_to_update=0,
            unchanged=0,
            skipped=(),
            corrupt=(),
            blocked=(),
            prepare_error=ExitCode.PUSH_ABORT,
        )
        with (
            patch.object(RuntimeResolver, "sync_run", return_value=run),
            patch.object(service._sync, "load_push_preview", return_value=blocked),
        ):
            preview, diffs, result = service.load_push_plan(_push("/tmp/w.txt"))
        self.assertEqual(result, ExitCode.PUSH_ABORT)

    def test_execute_push_dry_run_success_path(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "dict.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(dict_path, ["alpha"], "utf-8", False, quiet=True)
            run = make_sync_run(
                wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            service = SpellSyncService(enable_file_logging=False)
            with patch(
                "spell_sync.application._runtime_factory.discover_dictionaries",
                return_value=run.context.dictionaries,
            ):
                with patch.object(RuntimeResolver, "sync_run", return_value=run):
                    preview = service.load_push_preview(_push(wordlist))
                    execution = service.execute_push_dry_run(_push(wordlist), preview)
            self.assertIsInstance(execution.result, PushResult)

    def test_pull_and_push_execution_from_result_paths(self):
        service = SpellSyncService(enable_file_logging=False)
        pull_preview = PullPreview(
            wordlist_path="/tmp/w.txt",
            additions=3,
            before_count=1,
            after_count=4,
            sources_used=(),
            sources_skipped=(),
            source_rows=(),
            warnings=(),
            created_at="t",
            plan_identifier="pull",
            merged_words=(),
        )
        pull_execution = service.pull_execution_from_result(pull_preview, (1, 4))
        self.assertEqual(pull_execution.result, (1, 4))

        bad_prepared = MagicMock()
        bad_prepared.targets = [object()]
        push_execution = service.push_execution_from_result(
            bad_prepared,
            PushResult(1, ("a",), ()),
        )
        self.assertIsInstance(push_execution.result, PushResult)
        self.assertIsNone(push_execution.push_preview)


if __name__ == "__main__":
    unittest.main()
