"""Architecture guards for Phase 3 explicit runtime."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from unittest.mock import patch

from spell_sync.application.project_resolution import effective_push_strict
from spell_sync.application.requests import ProjectRef, PushRequest
from spell_sync.application.runtime_resolver import RuntimeResolver
from spell_sync.command_helpers import mutating_command_scope_for
from spell_sync.push_journal import JournalLoadResult, JournalLoadStatus
from spell_sync.settings import ConfigLoadResult, ConfigStatus
from spell_sync.sync_context import RuntimeContext
from spell_sync.validated_runtime import ValidatedRuntime

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SPELL_SYNC = _REPO_ROOT / "spell_sync"


def _source_has_contextvar(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "contextvars":
            return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "contextvars":
                    return True
    return False


class TestExplicitRuntimeGuards(unittest.TestCase):
    def test_settings_and_command_helpers_have_no_contextvar(self) -> None:
        for rel in ("settings.py", "command_helpers.py"):
            path = _SPELL_SYNC / rel
            self.assertFalse(
                _source_has_contextvar(path),
                msg=f"[ARCH-RT-001] {rel} must not import ContextVar",
            )

    def test_spell_sync_package_has_no_implicit_runtime_contextvars(self) -> None:
        hits: list[str] = []
        for path in _SPELL_SYNC.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "_active_settings" in text or "_active_validated" in text:
                hits.append(str(path.relative_to(_REPO_ROOT)))
        self.assertEqual(hits, [], msg=f"[ARCH-RT-002] implicit runtime symbols remain: {hits}")

    def test_runtime_resolver_bound_reuses_validated(self) -> None:
        context = RuntimeContext.build(Path("/tmp/wordlist.txt"), dictionaries=[])
        validated = ValidatedRuntime(
            context,
            ConfigLoadResult(ConfigStatus.ABSENT, {}, ()),
            JournalLoadResult(JournalLoadStatus.ABSENT, None),
        )
        resolver = RuntimeResolver(bound=validated)
        project = ProjectRef(wordlist=Path("/tmp/other.txt"))
        with patch("spell_sync.application.runtime_resolver.build_validated_runtime") as build:
            self.assertIs(resolver.validated(project), validated)
            build.assert_not_called()
        with patch("spell_sync.application.runtime_resolver.sync_run_for") as sync_run_for:
            run = resolver.sync_run(project)
            sync_run_for.assert_not_called()
            self.assertIs(run.context, context)

    def test_effective_push_strict_uses_explicit_config(self) -> None:
        request = PushRequest(project=ProjectRef())
        self.assertTrue(
            effective_push_strict(
                request,
                config={"push": {"strict": True}},
            )
        )
        self.assertFalse(
            effective_push_strict(
                request,
                config={"push": {"strict": False}},
            )
        )

    def test_runtime_resolver_sync_run_applies_strict_push_override(self) -> None:
        context = RuntimeContext.build(
            Path("/tmp/wordlist.txt"),
            dictionaries=[],
            strict_push=False,
        )
        validated = ValidatedRuntime(
            context,
            ConfigLoadResult(ConfigStatus.ABSENT, {}, ()),
            JournalLoadResult(JournalLoadStatus.ABSENT, None),
        )
        resolver = RuntimeResolver(bound=validated)
        run = resolver.sync_run(ProjectRef(), strict_push=True)
        self.assertTrue(run.strict_push)

    def test_application_exports_runtime_resolver(self) -> None:
        import spell_sync.application as application_pkg

        self.assertIs(application_pkg.RuntimeResolver, RuntimeResolver)

    def test_mutating_scope_reuses_bound_without_lock(self) -> None:
        context = RuntimeContext.build(Path("/tmp/wordlist.txt"), dictionaries=[])
        validated = ValidatedRuntime(
            context,
            ConfigLoadResult(ConfigStatus.VALID, {}, ()),
            JournalLoadResult(JournalLoadStatus.ABSENT, None),
        )
        with patch("spell_sync.command_helpers.operation_lock_scope_for") as lock_scope:
            with mutating_command_scope_for(
                Path("/tmp/wordlist.txt"),
                "push",
                bound=validated,
            ) as scope:
                self.assertIs(scope, validated)
            lock_scope.assert_not_called()


if __name__ == "__main__":
    unittest.main()
