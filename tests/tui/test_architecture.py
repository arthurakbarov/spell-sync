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


if __name__ == "__main__":
    unittest.main()
