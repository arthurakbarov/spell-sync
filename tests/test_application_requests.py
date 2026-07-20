"""Architecture and behavior tests for typed application requests."""

from __future__ import annotations

import ast
import importlib
import inspect
import io
import json
import pkgutil
import unittest
from contextlib import redirect_stdout
from dataclasses import is_dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

from spell_sync.application import requests as requests_mod
from spell_sync.application.requests import (
    ProjectRef,
    PushRequest,
    effective_push_strict,
    resolve_project_wordlist,
)
from spell_sync.application.service import SpellSyncService
from spell_sync.cli import COMMANDS
from spell_sync.cli_options import CliOptions
from spell_sync.cli_request_adapter import (
    config_check_request,
    doctor_request,
    lint_request,
    project_ref,
    pull_request,
    push_request,
    recovery_request,
    setup_request,
    status_request,
    support_report_request,
    target_settings_request,
)
from spell_sync.exit_codes import ExitCode


def _module_imports(module_name: str, banned: tuple[str, ...]) -> list[str]:
    module = importlib.import_module(module_name)
    source_path = getattr(module, "__file__", "") or ""
    if not source_path.endswith(".py"):
        return []
    tree = ast.parse(Path(source_path).read_text(encoding="utf-8"))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for token in banned:
                    if token in alias.name:
                        hits.append(f"{module_name}: import {alias.name}")
        if isinstance(node, ast.ImportFrom) and node.module:
            for token in banned:
                if token in node.module:
                    hits.append(f"{module_name}: from {node.module}")
    return hits


class TestApplicationRequests(unittest.TestCase):
    def test_request_dataclasses_are_frozen(self) -> None:
        for name in (
            "ProjectRef",
            "StatusRequest",
            "PullRequest",
            "PushRequest",
            "RecoveryRequest",
            "SetupRequest",
            "TargetSettingsRequest",
            "SupportReportRequest",
        ):
            cls = getattr(requests_mod, name)
            self.assertTrue(is_dataclass(cls))
            self.assertTrue(getattr(cls, "__dataclass_params__").frozen, msg=name)

    def test_requests_do_not_import_cli_or_textual(self) -> None:
        banned = ("cli_options", "cli_request_adapter", "argparse", "textual")
        source_path = Path(requests_mod.__file__ or "")
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for token in banned:
                        if token in alias.name:
                            self.fail(f"requests imports {alias.name}")
            if isinstance(node, ast.ImportFrom) and node.module:
                for token in banned:
                    if token in node.module:
                        self.fail(f"requests imports from {node.module}")

    def test_application_layer_does_not_import_cli_options(self) -> None:
        import spell_sync.application as application_pkg

        for module_info in pkgutil.walk_packages(
            application_pkg.__path__,
            application_pkg.__name__ + ".",
        ):
            for hit in _module_imports(
                module_info.name, ("cli_options", "cli_request_adapter", "argparse")
            ):
                self.fail(hit)

    def test_tui_does_not_import_cli_options(self) -> None:
        import spell_sync.tui as tui_pkg

        for module_info in pkgutil.walk_packages(tui_pkg.__path__, tui_pkg.__name__ + "."):
            for hit in _module_imports(module_info.name, ("cli_options", "cli_request_adapter")):
                self.fail(hit)

    def test_cli_adapter_project_ref_semantics(self) -> None:
        absent = project_ref(CliOptions())
        self.assertIsNone(absent.wordlist)
        explicit = project_ref(CliOptions(wordlist="/tmp/w.txt"))
        self.assertEqual(explicit.wordlist, Path("/tmp/w.txt"))

    def test_relative_wordlist_resolution(self) -> None:
        project = ProjectRef(wordlist=Path("relative/wordlist.txt"))
        resolved = resolve_project_wordlist(project)
        self.assertEqual(resolved, Path("relative/wordlist.txt"))

    def test_pull_add_from_mapping(self) -> None:
        request = pull_request(CliOptions(wordlist="/tmp/w.txt", add_from="/tmp/extra.txt"))
        self.assertEqual(request.add_from, Path("/tmp/extra.txt"))

    def test_push_strict_override_tri_state(self) -> None:
        unset = PushRequest(project=ProjectRef())
        self.assertIsNone(unset.strict_override)
        explicit = push_request(CliOptions(strict=True))
        self.assertTrue(explicit.strict_override)
        self.assertTrue(effective_push_strict(explicit))

    def test_status_verbose_maps_to_include_word_diffs(self) -> None:
        quiet = status_request(CliOptions())
        verbose = status_request(CliOptions(verbose=True))
        self.assertFalse(quiet.include_word_diffs)
        self.assertTrue(verbose.include_word_diffs)

    def test_service_accepts_status_request(self) -> None:
        service = SpellSyncService(enable_file_logging=False)
        signature = inspect.signature(service.load_status)
        self.assertEqual(
            list(signature.parameters),
            ["request"],
        )

    def test_cli_commands_have_request_mappers_or_are_presentation_only(self) -> None:
        mapped = {
            "status",
            "doctor",
            "pull",
            "push",
            "recover",
            "support-report",
            "config-check",
            "lint",
            "ui",
        }
        presentation_only = {"version", "init", "plan"}
        self.assertEqual(set(COMMANDS), mapped | presentation_only)

    def test_remaining_cli_request_mappers(self) -> None:
        opts = CliOptions(wordlist="/tmp/w.txt", fix=True, strict=True)
        self.assertIsInstance(doctor_request(opts).project, ProjectRef)
        self.assertIsInstance(recovery_request(opts).project, ProjectRef)
        self.assertTrue(setup_request(CliOptions()).allow_new_project_wizard)
        self.assertFalse(setup_request(opts).allow_new_project_wizard)
        self.assertIsInstance(target_settings_request(opts).project, ProjectRef)
        self.assertIsInstance(support_report_request(opts).project, ProjectRef)
        self.assertIsInstance(config_check_request(opts).project, ProjectRef)
        lint = lint_request(opts)
        self.assertTrue(lint.fix)
        self.assertTrue(lint.strict)

    def test_project_scope_helpers_cover_json_and_early_returns(self) -> None:
        from spell_sync import command_helpers
        from spell_sync.operation_lock import OperationLocked, OperationLockInfo
        from spell_sync.push_journal import JournalLoadResult, JournalLoadStatus
        from spell_sync.settings import ConfigLoadResult, ConfigStatus

        project = ProjectRef(wordlist=Path("/tmp/w.txt"))
        absent = JournalLoadResult(JournalLoadStatus.ABSENT, None)
        self.assertIsNone(command_helpers.unfinished_journal_exit_from_result_for("push", absent))
        completed = JournalLoadResult(JournalLoadStatus.VALID_COMPLETED, None)
        self.assertIsNone(
            command_helpers.unfinished_journal_exit_from_result_for("push", completed)
        )
        invalid = ConfigLoadResult(
            status=ConfigStatus.SYNTAX_ERROR,
            config=None,
            diagnostics=(),
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = command_helpers.invalid_config_exit_from_scope(
                "push",
                invalid,
                json_output=True,
            )
        self.assertEqual(code, int(ExitCode.PUSH_ABORT))
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["reason"], "invalid_config")

        info = OperationLockInfo(1, "t", "push", "/tmp/w.txt")
        with patch(
            "spell_sync.command_helpers.acquire_operation_lock",
            side_effect=OperationLocked(info, Path("/tmp/.lock")),
        ):
            with command_helpers.operation_lock_scope(
                CliOptions(json_output=True),
                "push",
            ) as lock_exit:
                self.assertEqual(lock_exit, int(ExitCode.PUSH_ABORT))

        with patch(
            "spell_sync.command_helpers.build_validated_runtime",
        ) as build:
            build.return_value = MagicMock(
                config_result=invalid,
                journal_result=absent,
            )
            gen = command_helpers.mutating_command_scope_for(
                project,
                "push",
                json_output=True,
            )
            scope = gen.__enter__()
            self.assertEqual(scope, int(ExitCode.PUSH_ABORT))
            gen.__exit__(None, None, None)


if __name__ == "__main__":
    unittest.main()
