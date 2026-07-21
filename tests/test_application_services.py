#!/usr/bin/env python3
"""Architecture guards for Phase 4 focused application services."""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import MagicMock, patch

from spell_sync.application.reports import OperationOutcome
from spell_sync.application.service import SpellSyncService
from spell_sync.application.services import (
    DiagnosticsService,
    InspectionService,
    RecoveryService,
    SyncService,
)
from spell_sync.application.services.context import ApplicationContext
from spell_sync.diagnostics.history_store import OperationHistoryStore
from spell_sync.diagnostics.paths import resolve_app_state_paths
from spell_sync.exit_codes import ExitCode
from spell_sync.push_prepared import PreparedPush
from spell_sync.sync_models import PushResult

_REPO_ROOT = Path(__file__).resolve().parents[1]
_APPLICATION = _REPO_ROOT / "spell_sync" / "application"
_SERVICES = _APPLICATION / "services"
_FACADE = _APPLICATION / "service.py"

_FACADE_DELEGATION: dict[str, str] = {
    "mutating_config_exit_code": "_sync",
    "load_operation_history": "_diagnostics",
    "clear_operation_history": "_diagnostics",
    "technical_log_path": "_diagnostics",
    "read_technical_log_tail": "_diagnostics",
    "load_support_report": "_diagnostics",
    "load_status": "_inspection",
    "load_status_detail": "_inspection",
    "load_dashboard": "_inspection",
    "load_push_preview": "_sync",
    "load_doctor": "_inspection",
    "load_doctor_report": "_inspection",
    "load_doctor_targets": "_inspection",
    "load_push_removals": "_sync",
    "load_push_plan": "_sync",
    "execute_push_dry_run": "_sync",
    "prepare_pull": "_sync",
    "execute_pull": "_sync",
    "pull_execution_from_result": "_sync",
    "push_execution_from_result": "_sync",
    "execute_push_preview": "_sync",
    "inspect_recovery": "_recovery",
    "execute_recovery": "_recovery",
    "execute_recovery_cleanup": "_recovery",
    "execute_recovery_discard": "_recovery",
    "inspect_project_setup": "_setup",
    "discover_setup_targets": "_setup",
    "prepare_project_setup": "_setup",
    "execute_project_setup": "_setup",
    "validate_setup_wordlist": "_setup",
    "build_setup_report": "_diagnostics",
    "load_target_settings": "_target_settings",
    "prepare_target_settings_update": "_target_settings",
    "execute_target_settings_update": "_target_settings",
    "build_target_settings_report": "_diagnostics",
    "build_push_report": "_diagnostics",
    "build_pull_report": "_diagnostics",
    "build_support_report": "_diagnostics",
    "build_recovery_report": "_diagnostics",
}

_BANNED_FACADE_IMPORT_ROOTS = (
    "_operation_deps",
    "push_journal",
    "push_transaction",
    "recover_from_journal",
    "execute_prepared_push",
    "plan_fingerprint_conflict",
)


def _facade_class() -> ast.ClassDef:
    tree = ast.parse(_FACADE.read_text(encoding="utf-8"))
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "SpellSyncService"
    )


def _delegation_target(call: ast.Call) -> tuple[str, str] | None:
    func = call.func
    if not isinstance(func, ast.Attribute):
        return None
    if not isinstance(func.value, ast.Attribute):
        return None
    if not isinstance(func.value.value, ast.Name) or func.value.value.id != "self":
        return None
    return func.value.attr, func.attr


class TestApplicationServiceArchitecture(unittest.TestCase):
    def test_facade_is_thinner_than_pre_phase4_monolith(self) -> None:
        line_count = len(_FACADE.read_text(encoding="utf-8").splitlines())
        self.assertLess(line_count, 400, msg=f"facade still {line_count} lines")

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

    def test_facade_does_not_import_operation_deps_or_core_mutation_modules(self) -> None:
        tree = ast.parse(_FACADE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for banned in _BANNED_FACADE_IMPORT_ROOTS:
                    self.assertNotIn(
                        banned,
                        node.module,
                        msg=f"facade imports {node.module}",
                    )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for banned in _BANNED_FACADE_IMPORT_ROOTS:
                        self.assertNotIn(banned, alias.name, msg=f"facade imports {alias.name}")

    def test_facade_has_no_private_operation_methods(self) -> None:
        cls = _facade_class()
        private_methods = [
            node.name
            for node in cls.body
            if isinstance(node, ast.FunctionDef)
            and node.name.startswith("_")
            and not node.name.startswith("__")
        ]
        self.assertEqual(private_methods, [], msg=f"unexpected private methods: {private_methods}")

    def test_facade_public_methods_delegate_to_focused_services(self) -> None:
        cls = _facade_class()
        for node in cls.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name.startswith("_") or node.name == "__init__":
                continue
            if any(
                isinstance(dec, ast.Name) and dec.id == "property" for dec in node.decorator_list
            ):
                continue
            expected_service = _FACADE_DELEGATION.get(node.name)
            self.assertIsNotNone(expected_service, msg=f"missing delegation map for {node.name}")
            body = [stmt for stmt in node.body if not isinstance(stmt, ast.Expr)]
            self.assertEqual(len(body), 1, msg=f"{node.name} must contain one statement")
            stmt = body[0]
            self.assertIsInstance(stmt, ast.Return, msg=f"{node.name} must return")
            assert isinstance(stmt, ast.Return)
            self.assertIsInstance(stmt.value, ast.Call, msg=f"{node.name} must call a service")
            assert isinstance(stmt.value, ast.Call)
            target = _delegation_target(stmt.value)
            self.assertIsNotNone(target, msg=f"{node.name} must delegate via self._service")
            service_attr, method_name = target
            self.assertEqual(service_attr, expected_service, msg=node.name)
            self.assertEqual(method_name, node.name, msg=node.name)

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

    def test_application_context_dependencies_are_frozen(self) -> None:
        paths = resolve_app_state_paths()
        store = OperationHistoryStore(paths)
        ctx = ApplicationContext(
            runtime=MagicMock(),
            history_store=store,
            state_paths=paths,
        )
        with self.assertRaises(FrozenInstanceError):
            ctx.runtime = MagicMock()  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            ctx.history_store = OperationHistoryStore(paths)  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            ctx.state_paths = paths  # type: ignore[misc]

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

    def test_sync_run_push_for_run_outcome_branches(self) -> None:
        service = SpellSyncService(enable_file_logging=False)
        sync = service._sync  # noqa: SLF001 — focused service behavior check
        prepared = MagicMock(spec=PreparedPush)
        run = MagicMock()
        with patch.object(
            sync,
            "_execute_push_for_run",
            return_value=ExitCode.PUSH_ABORT,
        ):
            failed = sync._run_push_for_run(run, prepared, dry_run=False)
        self.assertEqual(failed.outcome, OperationOutcome.FAILED)
        with patch.object(
            sync,
            "_execute_push_for_run",
            return_value=PushResult(word_count=1, written=("a",), skipped=("b",)),
        ):
            warned = sync._run_push_for_run(run, prepared, dry_run=False)
        self.assertEqual(warned.outcome, OperationOutcome.COMPLETED_WITH_WARNINGS)


if __name__ == "__main__":
    unittest.main()
