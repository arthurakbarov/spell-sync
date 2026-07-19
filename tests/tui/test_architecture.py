"""Architecture boundary tests for the TUI package."""

from __future__ import annotations

import ast
import importlib
import pkgutil
import unittest
from importlib import resources
from pathlib import Path
from unittest.mock import MagicMock, patch

import spell_sync.tui as tui_pkg
from spell_sync.application import SpellSyncService
from spell_sync.application.reports import PushPreview
from spell_sync.push_prepared import PreparedPush
from spell_sync.tui.controller import TuiController
from tests.tui.fake_service import fake_service


class TestTuiArchitecture(unittest.TestCase):
    def test_tui_does_not_import_sync_run(self):
        for module_info in pkgutil.walk_packages(tui_pkg.__path__, tui_pkg.__name__ + "."):
            module = importlib.import_module(module_info.name)
            source_path = getattr(module, "__file__", "") or ""
            if not source_path.endswith(".py"):
                continue
            tree = ast.parse(Path(source_path).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(
                            "sync_run",
                            alias.name,
                            msg=f"{module_info.name} imports {alias.name}",
                        )
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn(
                        "sync_run",
                        node.module,
                        msg=f"{module_info.name} imports from {node.module}",
                    )

    def test_tui_does_not_import_low_level_writers(self):
        banned = (
            "push_transaction",
            "push_render",
            "atomic_write",
            "execute_prepared_push",
            "PushJournalSession",
            "recover_from_journal",
            "discard_journal",
            "push_journal",
        )
        for module_info in pkgutil.walk_packages(tui_pkg.__path__, tui_pkg.__name__ + "."):
            module = importlib.import_module(module_info.name)
            source = Path(module.__file__ or "").read_text(encoding="utf-8")
            for token in banned:
                self.assertNotIn(token, source, msg=f"{module_info.name} references {token}")

    def test_application_does_not_import_textual(self):
        import spell_sync.application as application_pkg

        for module_info in pkgutil.walk_packages(
            application_pkg.__path__,
            application_pkg.__name__ + ".",
        ):
            module = importlib.import_module(module_info.name)
            source = Path(module.__file__ or "").read_text(encoding="utf-8").lower()
            self.assertNotIn("textual", source, msg=module_info.name)

    def test_tui_does_not_shell_out_to_cli(self):
        for module_info in pkgutil.walk_packages(tui_pkg.__path__, tui_pkg.__name__ + "."):
            module = importlib.import_module(module_info.name)
            source = Path(module.__file__ or "").read_text(encoding="utf-8").lower()
            self.assertNotIn("subprocess", source, msg=module_info.name)
            self.assertNotIn("os.system", source, msg=module_info.name)

    def test_push_preview_carries_prepared_push(self):
        prepared = PreparedPush(
            ctx=MagicMock(),
            plan=MagicMock(),
            targets=(),
            dictionaries=(),
            skipped_unreadable=(),
            skipped_corrupt=(),
            skipped_blocked=(),
            wordlist_rendered=None,
            wordlist_needs_write=False,
        )
        preview = PushPreview(
            prepared=prepared,
            targets=(),
            additions=0,
            removals=0,
            warnings=(),
            created_at="2026-01-01T00:00:00+00:00",
            plan_identifier="abc12345",
            targets_to_update=0,
            unchanged=0,
            skipped=(),
            corrupt=(),
            blocked=(),
        )
        self.assertIs(preview.prepared, prepared)

    def test_textual_css_is_packaged(self):
        css_path = resources.files("spell_sync.tui").joinpath("app.tcss")
        self.assertTrue(css_path.is_file())

    def test_dashboard_loads_via_service_only(self):
        controller = TuiController(fake_service(), MagicMock())
        with patch.object(controller._service, "load_dashboard") as load_dashboard:
            controller.dashboard()
        load_dashboard.assert_called_once()

    def test_push_execution_goes_through_service(self):
        service = fake_service()
        controller = TuiController(service, MagicMock())
        preview = service.preview
        controller._active_push_preview = preview
        execution = controller.execute_push(preview)
        self.assertEqual(service.execute_push_calls, 1)
        self.assertIs(service.last_executed_prepared, preview.prepared)
        self.assertIs(execution.prepared, preview.prepared)

    def test_confirmation_uses_preview_counts(self):
        from spell_sync.tui.screens.push_confirm_screen import PushConfirmScreen
        from tests.tui.fake_service import sample_preview

        preview = sample_preview(removals=6, additions=28)
        screen = PushConfirmScreen(TuiController(fake_service(), MagicMock()), preview)
        self.assertEqual(screen._preview.removals, 6)
        self.assertEqual(screen._preview.additions, 28)

    def test_removal_words_not_in_operation_events(self):
        from spell_sync.application.events import OperationEvent

        # Event schema has no word payload fields.
        self.assertNotIn("words", OperationEvent.__annotations__)
        self.assertNotIn("removal_words", OperationEvent.__annotations__)

    def test_tui_setup_goes_through_service(self):
        service = fake_service()
        controller = TuiController(service, MagicMock())
        controller.set_setup_wordlist(Path("/tmp/project/wordlist.txt"))
        controller.prepare_setup_preview()
        self.assertIsNotNone(controller._setup_prepared)

    def test_tui_does_not_import_project_setup_execute(self):
        banned = ("atomic_write", "execute_project_setup", "prepare_project_setup")
        for name in (
            "setup_welcome_screen.py",
            "setup_targets_screen.py",
            "target_settings_screen.py",
        ):
            source = Path(tui_pkg.__file__).parent / "screens" / name
            text = source.read_text(encoding="utf-8")
            for token in banned:
                self.assertNotIn(token, text, msg=f"{name} references {token}")

    def test_target_settings_goes_through_service(self):
        service = fake_service()
        controller = TuiController(service, MagicMock())
        controller.begin_target_settings()
        prepared = controller.prepare_target_settings_update()
        controller.execute_target_settings_update(prepared)
        self.assertEqual(service.execute_target_settings_calls, 1)

    def test_target_settings_screen_uses_controller_selection(self):
        source = (
            Path(tui_pkg.__file__).parent / "screens" / "target_settings_screen.py"
        ).read_text(encoding="utf-8")
        self.assertIn("toggle_target_settings_target", source)
        self.assertNotIn("discover_dictionaries", source)
        self.assertNotIn("render_project_config", source)
        self.assertNotIn("atomic_write", source)

    def test_setup_targets_screen_uses_controller_selection(self):
        source = (Path(tui_pkg.__file__).parent / "screens" / "setup_targets_screen.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("toggle_setup_target", source)
        self.assertNotIn("discover_dictionaries", source)
        self.assertNotIn("render_project_config", source)

    def test_prepared_setup_exposes_selected_target_ids(self):
        from spell_sync.project_setup.draft import SetupDraft
        from spell_sync.project_setup.prepare import prepare_project_setup

        prepared = prepare_project_setup(
            SetupDraft(Path("/tmp/x/wordlist.txt"), ("chrome",), create_wordlist=True)
        )
        self.assertEqual(prepared.selected_target_ids, ("chrome",))

    def test_cli_init_and_tui_share_service_entrypoint(self):
        import tempfile

        from spell_sync.cli_options import CliOptions
        from spell_sync.commands import cmd_init
        from spell_sync.project_setup.draft import SetupDraft
        from spell_sync.project_setup.prepare import prepare_project_setup

        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            prepared = prepare_project_setup(
                SetupDraft(wordlist, (), create_wordlist=True),
            )
            with patch.object(
                SpellSyncService,
                "execute_project_setup",
            ) as execute:
                with patch.object(SpellSyncService, "prepare_project_setup", return_value=prepared):
                    with patch.object(SpellSyncService, "build_setup_report"):
                        cmd_init(CliOptions(wordlist=str(wordlist)))
            execute.assert_called_once()

    def test_tui_does_not_import_logging_handlers(self):
        for module_info in pkgutil.walk_packages(tui_pkg.__path__, tui_pkg.__name__ + "."):
            module = importlib.import_module(module_info.name)
            source = Path(module.__file__ or "").read_text(encoding="utf-8")
            self.assertNotIn("logging.handlers", source, msg=module_info.name)

    def test_tui_does_not_open_history_or_log_files(self):
        banned = (
            "operation-history.jsonl",
            "RotatingFileHandler",
            ".unlink(",
            "write_text(",
            "write_bytes(",
        )
        for module_info in pkgutil.walk_packages(tui_pkg.__path__, tui_pkg.__name__ + "."):
            module = importlib.import_module(module_info.name)
            source_path = module.__file__ or ""
            if not source_path.endswith(".py"):
                continue
            source = Path(source_path).read_text(encoding="utf-8")
            for token in banned:
                self.assertNotIn(token, source, msg=f"{module_info.name} references {token}")

    def test_history_record_has_no_word_fields(self):
        from spell_sync.diagnostics.history_record import OperationHistoryRecord

        allowed_counts = {
            "added_words",
            "additions",
            "removals",
            "updated_targets",
            "unchanged_targets",
            "skipped_targets",
            "failed_targets",
        }
        forbidden = (
            "wordlist",
            "dictionary",
            "snapshot",
            "toml",
            "secret",
            "token",
            "removal_words",
        )
        for name in OperationHistoryRecord.__dataclass_fields__:
            if name in allowed_counts:
                continue
            lowered = name.lower()
            for token in forbidden:
                self.assertNotIn(token, lowered, msg=name)

    def test_report_screen_does_not_append_history(self):
        source = (Path(tui_pkg.__file__).parent / "screens" / "report_screen.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("OperationHistoryStore", source)
        self.assertNotIn("build_history_record", source)
        self.assertNotIn("build_setup_report", source)
        self.assertNotIn("build_push_report", source)

    def test_review_flow_uses_existing_pull_push_services(self):
        source = (Path(tui_pkg.__file__).parent / "screens" / "review_update_screen.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("prepare_review_pull", source)
        self.assertIn("prepare_review_push", source)
        self.assertIn("OperationScreen", source)
        self.assertIn("PullConfirmScreen", source)
        self.assertIn("PushConfirmScreen", source)
        self.assertNotIn("execute_prepared_push", source)
        self.assertNotIn("atomic_write", source)

    def test_review_session_not_persistent_record(self):
        from spell_sync.application.review_session import ReviewSession
        from spell_sync.diagnostics.history_record import OperationHistoryRecord

        session_fields = set(ReviewSession.__dataclass_fields__)
        history_fields = set(OperationHistoryRecord.__dataclass_fields__)
        self.assertFalse(session_fields & history_fields)
        source = (Path(tui_pkg.__file__).parent / "screens" / "review_update_screen.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("OperationHistoryStore", source)
        self.assertNotIn("build_history_record", source)
        controller_source = (Path(tui_pkg.__file__).parent / "controller.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("clear_review_session", controller_source)
        self.assertNotIn("_review_session: ReviewSession = ReviewSession", controller_source)


if __name__ == "__main__":
    unittest.main()
