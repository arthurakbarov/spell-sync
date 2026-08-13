"""Architecture guards for explicit runtime wiring."""

import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spell_sync.application.project_resolution import effective_push_strict
from spell_sync.application.requests import ProjectRef, PushRequest
from spell_sync.application.runtime_resolver import RuntimeResolver
from spell_sync.push_journal import JournalLoadResult, JournalLoadStatus
from spell_sync.resolved_runtime import ProjectRuntimeMismatchError, ResolvedRuntime
from spell_sync.runtime_identity import build_runtime_identity
from spell_sync.runtime_settings import RuntimeSettings
from spell_sync.settings import ConfigLoadResult, ConfigStatus
from spell_sync.sync_context import RuntimeContext

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


def _source_has_global_mutation_state(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {
                    "_mutating_scope_validated",
                    "_settings_cache",
                    "_settings_cache_key",
                }:
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

    def test_no_module_level_mutation_or_settings_cache(self) -> None:
        for rel in ("settings.py", "command_helpers.py"):
            path = _SPELL_SYNC / rel
            self.assertFalse(
                _source_has_global_mutation_state(path),
                msg=f"[ARCH-RT-003] {rel} must not keep module-level runtime cache",
            )

    def test_spell_sync_package_has_no_implicit_runtime_contextvars(self) -> None:
        hits: list[str] = []
        for path in _SPELL_SYNC.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "_active_settings" in text or "_active_validated" in text:
                hits.append(str(path.relative_to(_REPO_ROOT)))
        self.assertEqual(hits, [], msg=f"[ARCH-RT-002] implicit runtime symbols remain: {hits}")

    def test_runtime_resolver_bound_reuses_validated(self) -> None:
        context = RuntimeContext.build(
            Path("/tmp/wordlist.txt"),
            [],
            settings=RuntimeSettings.defaults(),
        )
        validated = ResolvedRuntime(
            context,
            ConfigLoadResult(ConfigStatus.ABSENT, {}, ()),
            JournalLoadResult(JournalLoadStatus.ABSENT, None),
            build_runtime_identity(context),
        )
        resolver = RuntimeResolver(bound=validated)
        project = ProjectRef(wordlist=Path("/tmp/other.txt"))
        with patch("spell_sync.application._runtime_factory._build_resolved_runtime") as build:
            with self.assertRaises(ProjectRuntimeMismatchError):
                resolver.resolve_read(project)
            build.assert_not_called()

    def test_effective_push_strict_uses_explicit_settings(self) -> None:
        request = PushRequest(project=ProjectRef())
        settings = RuntimeSettings.from_config_dict({"push": {"strict": True}})
        self.assertTrue(effective_push_strict(request, settings=settings))
        relaxed = RuntimeSettings.from_config_dict({"push": {"strict": False}})
        self.assertFalse(effective_push_strict(request, settings=relaxed))

    def test_runtime_resolver_sync_run_applies_strict_push_override(self) -> None:
        context = RuntimeContext.build(
            Path("/tmp/wordlist.txt"),
            [],
            settings=RuntimeSettings.defaults(),
            strict_push=False,
        )
        validated = ResolvedRuntime(
            context,
            ConfigLoadResult(ConfigStatus.ABSENT, {}, ()),
            JournalLoadResult(JournalLoadStatus.ABSENT, None),
            build_runtime_identity(context),
        )
        resolver = RuntimeResolver(bound=validated)
        run = resolver.sync_run(ProjectRef(wordlist=Path("/tmp/wordlist.txt")), strict_push=True)
        self.assertTrue(run.strict_push)

    def test_application_exports_runtime_resolver(self) -> None:
        import spell_sync.application as application_pkg

        self.assertIs(application_pkg.RuntimeResolver, RuntimeResolver)

    def test_mutation_scope_acquires_lock_despite_bound_preview(self) -> None:
        context = RuntimeContext.build(
            Path("/tmp/wordlist.txt"),
            [],
            settings=RuntimeSettings.defaults(),
        )
        validated = ResolvedRuntime(
            context,
            ConfigLoadResult(ConfigStatus.VALID, {}, ()),
            JournalLoadResult(JournalLoadStatus.ABSENT, None),
            build_runtime_identity(context),
        )
        fresh = ResolvedRuntime(
            context,
            ConfigLoadResult(ConfigStatus.VALID, {}, ()),
            JournalLoadResult(JournalLoadStatus.ABSENT, None),
            build_runtime_identity(context),
        )
        resolver = RuntimeResolver(bound=validated)
        with patch("spell_sync.application.mutation_scope.operation_lock_scope_for") as lock_scope:
            lock_scope.return_value.__enter__.return_value = None
            lock_scope.return_value.__exit__.return_value = False
            with patch(
                "spell_sync.application.mutation_scope._build_resolved_runtime",
                return_value=fresh,
            ) as build:
                with resolver.mutation_scope(
                    ProjectRef(wordlist=Path("/tmp/wordlist.txt")),
                    "push",
                ) as scope:
                    self.assertIs(scope, fresh)
                lock_scope.assert_called_once()
                build.assert_called_once()

    def test_effective_push_strict_requires_explicit_settings(self) -> None:
        with self.assertRaises(ValueError):
            effective_push_strict(PushRequest(project=ProjectRef()))

    def test_assert_bound_project_noop_without_bound(self) -> None:
        RuntimeResolver()._assert_bound_project(ProjectRef())

    def test_settings_helpers_use_defaults_for_invalid_types(self) -> None:
        from spell_sync.runtime_settings import RuntimeSettings

        cfg = {
            "push": {"strict": "bad", "guard_wordlist_max": "bad"},
            "io": {"backup_keep": "bad"},
            "neovim": {"mkspell_after_push": "bad"},
        }
        settings = RuntimeSettings.from_config_dict(cfg)
        self.assertFalse(settings.push.strict)
        self.assertEqual(settings.push.guard_wordlist_max, 10)
        self.assertEqual(settings.io.backup_keep, 3)
        self.assertFalse(settings.neovim.mkspell_after_push)
        valid = RuntimeSettings.from_config_dict(
            {
                "push": {"guard_wordlist_max": 11},
                "io": {"backup_keep": 12},
                "neovim": {"mkspell_after_push": False},
            }
        )
        self.assertEqual(valid.push.guard_wordlist_max, 11)
        self.assertEqual(valid.io.backup_keep, 12)
        self.assertFalse(valid.neovim.mkspell_after_push)

    def test_sync_run_for_applies_strict_push_override(self) -> None:
        from spell_sync.sync_run import sync_run_for

        context = RuntimeContext.build(
            Path("/tmp/wordlist.txt"),
            [],
            settings=RuntimeSettings.defaults(),
            strict_push=False,
        )
        validated = ResolvedRuntime(
            context,
            ConfigLoadResult(ConfigStatus.ABSENT, {}, ()),
            JournalLoadResult(JournalLoadStatus.ABSENT, None),
            build_runtime_identity(context),
        )
        run = sync_run_for(validated, strict_push=True)
        self.assertTrue(run.strict_push)

    def test_project_a_b_a_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as da, tempfile.TemporaryDirectory() as db:
            wordlist_a = Path(da) / "wordlist.txt"
            wordlist_b = Path(db) / "wordlist.txt"
            wordlist_a.write_text("alpha\n", encoding="utf-8")
            wordlist_b.write_text("beta\n", encoding="utf-8")
            (Path(da) / "spell-sync.toml").write_text(
                "[dictionaries]\nchrome = true\n",
                encoding="utf-8",
            )
            (Path(db) / "spell-sync.toml").write_text(
                "[dictionaries]\nchrome = false\n",
                encoding="utf-8",
            )
            resolver = RuntimeResolver()
            project_a = ProjectRef(wordlist=wordlist_a)
            project_b = ProjectRef(wordlist=wordlist_b)
            resolved_a1 = resolver.resolve_read(project_a)
            resolved_b = resolver.resolve_read(project_b)
            resolved_a2 = resolver.resolve_read(project_a)
            self.assertTrue(resolved_a1.context.settings.dictionaries.chrome)
            self.assertFalse(resolved_b.context.settings.dictionaries.chrome)
            self.assertTrue(resolved_a2.context.settings.dictionaries.chrome)
            self.assertIsNot(resolved_a1, resolved_b)
            self.assertIsNot(resolved_a1.context, resolved_b.context)

    def test_external_config_edit_visible_on_next_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            config = Path(d) / "spell-sync.toml"
            config.write_text("[dictionaries]\nchrome = true\n", encoding="utf-8")
            resolver = RuntimeResolver()
            project = ProjectRef(wordlist=wordlist)
            first = resolver.resolve_read(project)
            config.write_text("[dictionaries]\nchrome = false\n", encoding="utf-8")
            second = resolver.resolve_read(project)
            self.assertTrue(first.context.settings.dictionaries.chrome)
            self.assertFalse(second.context.settings.dictionaries.chrome)


class TestExplicitRuntimeCoverage(unittest.TestCase):
    def test_config_push_helpers_read_runtime_settings(self) -> None:
        from spell_sync.config import push_guard_local_min, push_strict_enabled

        settings = RuntimeSettings.defaults()
        self.assertIsInstance(push_strict_enabled(settings=settings), bool)
        self.assertIsInstance(push_guard_local_min(settings=settings), int)

    def test_support_report_tolerates_wordlist_load_failure(self) -> None:
        from spell_sync.application.requests import SupportReportRequest
        from spell_sync.application.support_report import build_support_report
        from spell_sync.diagnostics.types import OperationHistorySnapshot
        from tests.runtime_helpers import make_sync_run

        context = RuntimeContext.build(
            Path("/tmp/wordlist.txt"),
            [],
            settings=RuntimeSettings.defaults(),
        )
        resolved = ResolvedRuntime(
            context,
            ConfigLoadResult(ConfigStatus.VALID, {}, ()),
            JournalLoadResult(JournalLoadStatus.ABSENT, None),
            build_runtime_identity(context),
        )
        run = make_sync_run(wordlist=Path("/tmp/wordlist.txt"))
        service = type(
            "Service",
            (),
            {"load_operation_history": lambda self, limit=5: OperationHistorySnapshot(records=())},
        )()
        with patch.object(run, "load_wordlist", side_effect=OSError("boom")):
            with patch(
                "spell_sync.application.support_report.load_target_settings_snapshot",
                return_value=type("Snapshot", (), {"targets": ()})(),
            ):
                report = build_support_report(
                    service,
                    SupportReportRequest(project=ProjectRef()),
                    resolved=resolved,
                    run=run,
                )
        self.assertIsNone(report.project.wordlist_count)

    def test_running_apps_check_uses_defaults_without_prepared_settings(self) -> None:
        import spell_sync.commands as commands_mod
        from spell_sync.cli_options import CliOptions

        preview = type("Preview", (), {"prepared": None})()
        opts = CliOptions(yes=True, json_output=True)
        with patch.object(commands_mod, "confirm_chrome_before_push", return_value=True):
            with patch.object(commands_mod, "confirm_edge_before_push", return_value=True):
                with patch.object(commands_mod, "confirm_firefox_before_push", return_value=True):
                    with patch.object(
                        commands_mod,
                        "confirm_obsidian_before_push",
                        return_value=True,
                    ):
                        self.assertTrue(commands_mod._running_apps_check_for_push(opts, preview))

    def test_app_process_running_rules_cover_edge_and_firefox(self) -> None:
        import spell_sync.app_process_check as guard

        edge_rule = next(rule for rule in guard._RUNNING_APP_RULES if rule.name_prefix == "edge:")
        firefox_rule = next(
            rule for rule in guard._RUNNING_APP_RULES if rule.name_prefix == "firefox:"
        )
        with patch.object(guard, "is_edge_running", return_value=True):
            self.assertTrue(guard._rule_is_running(edge_rule))
        with patch.object(guard, "is_firefox_running", return_value=False):
            self.assertFalse(guard._rule_is_running(firefox_rule))


if __name__ == "__main__":
    unittest.main()
