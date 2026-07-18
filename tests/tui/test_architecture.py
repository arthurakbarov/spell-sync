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
        banned = ("push_transaction", "push_render", "atomic_write")
        for module_info in pkgutil.walk_packages(tui_pkg.__path__, tui_pkg.__name__ + "."):
            module = importlib.import_module(module_info.name)
            source = Path(module.__file__ or "").read_text(encoding="utf-8")
            for token in banned:
                self.assertNotIn(token, source, msg=f"{module_info.name} references {token}")

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


if __name__ == "__main__":
    unittest.main()
