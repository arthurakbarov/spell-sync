#!/usr/bin/env python3
"""Architecture guards for Phase 4 focused application services."""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from spell_sync.application.service import SpellSyncService
from spell_sync.application.services import (
    DiagnosticsService,
    InspectionService,
    RecoveryService,
    SyncService,
)
from spell_sync.application.services.context import ApplicationContext

_REPO_ROOT = Path(__file__).resolve().parents[1]
_APPLICATION = _REPO_ROOT / "spell_sync" / "application"
_SERVICES = _APPLICATION / "services"
_FACADE = _APPLICATION / "service.py"


class TestApplicationServiceArchitecture(unittest.TestCase):
    def test_facade_is_thinner_than_pre_phase4_monolith(self) -> None:
        line_count = len(_FACADE.read_text(encoding="utf-8").splitlines())
        self.assertLess(line_count, 450, msg=f"facade still {line_count} lines")

    def test_focused_service_modules_exist(self) -> None:
        for name in (
            "diagnostics.py",
            "inspection.py",
            "sync.py",
            "recovery.py",
            "setup.py",
            "target_settings.py",
            "context.py",
            "_shared.py",
        ):
            self.assertTrue((_SERVICES / name).is_file(), msg=name)

    def test_services_do_not_import_cli_or_tui(self) -> None:
        banned = ("spell_sync.cli", "spell_sync.commands", "spell_sync.tui", "textual")
        for path in _SERVICES.glob("*.py"):
            source = path.read_text(encoding="utf-8").lower()
            for token in banned:
                self.assertNotIn(token, source, msg=f"{path.name} references {token}")

    def test_core_modules_do_not_import_application_services(self) -> None:
        core_root = _REPO_ROOT / "spell_sync"
        skip = {"application", "cli.py", "commands.py", "__pycache__"}
        for path in core_root.rglob("*.py"):
            if any(part in skip for part in path.parts):
                continue
            if path.is_relative_to(_SERVICES):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn(
                        "application.services",
                        node.module,
                        msg=f"{path.relative_to(_REPO_ROOT)} imports {node.module}",
                    )

    def test_spell_sync_service_delegates_status_to_inspection(self) -> None:
        service = SpellSyncService(enable_file_logging=False)
        request = MagicMock()
        with patch.object(InspectionService, "load_status", return_value="status") as mocked:
            result = service.load_status(request)
        self.assertEqual(result, "status")
        mocked.assert_called_once_with(request)

    def test_spell_sync_service_delegates_push_preview_to_sync(self) -> None:
        service = SpellSyncService(enable_file_logging=False)
        request = MagicMock()
        with patch.object(SyncService, "load_push_preview", return_value="preview") as mocked:
            result = service.load_push_preview(request)
        self.assertEqual(result, "preview")
        mocked.assert_called_once_with(request)

    def test_spell_sync_service_delegates_recovery_to_recovery_service(self) -> None:
        service = SpellSyncService(enable_file_logging=False)
        request = MagicMock()
        with patch.object(RecoveryService, "inspect_recovery", return_value="preview") as mocked:
            result = service.inspect_recovery(request)
        self.assertEqual(result, "preview")
        mocked.assert_called_once_with(request)

    def test_application_context_carries_runtime_and_history(self) -> None:
        service = SpellSyncService(enable_file_logging=False)
        ctx = service._ctx  # noqa: SLF001 — architecture wiring check
        self.assertIsInstance(ctx, ApplicationContext)
        self.assertIs(ctx.runtime, service._runtime)
        self.assertIs(ctx.history_store, service._history_store)
        self.assertIs(ctx.state_paths, service._state_paths)

    def test_services_package_is_importable(self) -> None:
        import spell_sync.application.services as services_pkg

        for module_info in pkgutil.walk_packages(
            services_pkg.__path__,
            services_pkg.__name__ + ".",
        ):
            importlib.import_module(module_info.name)

    def test_diagnostics_finalize_report_is_canonical(self) -> None:
        source = inspect.getsource(DiagnosticsService.finalize_report)
        self.assertIn("build_history_record", source)
        self.assertIn("history_store.append", source)


if __name__ == "__main__":
    unittest.main()
