#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Runtime architecture: typed settings, dictionary registry, sync context."""

import ast
import inspect
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import spell_sync.settings as settings_mod
from spell_sync.application.requests import ProjectRef
from spell_sync.application.runtime_resolver import RuntimeResolver
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.dictionary_registry import DictionarySource, discover_from_sources
from spell_sync.push_journal import JournalLoadResult, JournalLoadStatus
from spell_sync.resolved_runtime import ResolvedRuntime
from spell_sync.runtime_identity import build_runtime_identity
from spell_sync.runtime_settings import RuntimeSettings
from spell_sync.settings import ConfigLoadResult, ConfigStatus
from spell_sync.sync_context import RuntimeContext
from spell_sync.sync_run import SyncRun, sync_run_for

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SPELL_SYNC = _REPO_ROOT / "spell_sync"
_COMMAND_MODULES = (
    _SPELL_SYNC / "commands.py",
    _SPELL_SYNC / "recover_cmd.py",
    _SPELL_SYNC / "support_report_cmd.py",
)


class TestSettingsFreshLoad(unittest.TestCase):
    def test_load_user_settings_reads_fresh_each_call(self):
        with tempfile.TemporaryDirectory() as d:
            project = Path(d) / "spell-sync.toml"
            project.write_text("[dictionaries]\nchrome = true\n", encoding="utf-8")
            with patch.object(settings_mod, "project_config_path", return_value=project):
                first, _ = settings_mod.load_project_settings_with_issues()
                project.write_text("[dictionaries]\nchrome = false\n", encoding="utf-8")
                second, _ = settings_mod.load_project_settings_with_issues()
            self.assertTrue(first["dictionaries"]["chrome"])
            self.assertFalse(second["dictionaries"]["chrome"])

    def test_config_load_result_runtime_settings(self):
        result = ConfigLoadResult(
            ConfigStatus.VALID,
            {"push": {"strict": True}},
            (),
        )
        self.assertTrue(result.runtime_settings().push.strict)


class TestDictionaryRegistry(unittest.TestCase):
    def test_discover_from_sources_skips_disabled(self):
        enabled = DictionarySource(
            "demo",
            lambda: False,
            lambda: [Dictionary("demo", "/tmp/demo.txt", DictionaryFormat.TEXT)],
        )
        self.assertEqual(discover_from_sources([enabled]), [])

    def test_discover_from_sources_includes_enabled(self):
        enabled = DictionarySource(
            "demo",
            lambda: True,
            lambda: [Dictionary("demo", "/tmp/demo.txt", DictionaryFormat.TEXT)],
        )
        result = discover_from_sources([enabled])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "demo")


class TestRuntimeContext(unittest.TestCase):
    def test_build_uses_explicit_wordlist_and_dictionaries(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "a.txt"
            dictionaries = [Dictionary("a", dict_path, DictionaryFormat.TEXT)]
            ctx = RuntimeContext.build(
                wordlist=wordlist,
                dictionaries=dictionaries,
                settings=RuntimeSettings.defaults(),
                strict_push=True,
            )
            self.assertEqual(ctx.wordlist_file, wordlist)
            self.assertEqual(ctx.dictionaries, tuple(dictionaries))
            self.assertTrue(ctx.strict_push)
            self.assertEqual(ctx.dictionary_names(), ("a",))

    def test_sync_run_exposes_strict_push(self):
        ctx = RuntimeContext.build(
            Path("/tmp/wordlist.txt"),
            [],
            settings=RuntimeSettings.defaults(),
            strict_push=True,
        )
        run = SyncRun(context=ctx)
        self.assertTrue(run.strict_push)

    def test_sync_run_wraps_context(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "a.txt"
            ctx = RuntimeContext.build(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
                settings=RuntimeSettings.defaults(),
            )
            run = SyncRun(context=ctx)
            self.assertIs(run.context, ctx)
            self.assertEqual(run.wordlist_file, wordlist)
            self.assertEqual(run.dictionaries[0].name, "a")

    def test_sync_run_for_requires_resolved_runtime(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("a\n", encoding="utf-8")
            resolved = RuntimeResolver().resolve_read(ProjectRef(wordlist=wordlist))
            run = sync_run_for(resolved)
            self.assertEqual(run.wordlist_file, wordlist)

    def test_sync_run_for_with_resolved_does_not_load_config(self):
        ctx = RuntimeContext.build(
            Path("/tmp/wordlist.txt"),
            [],
            settings=RuntimeSettings.defaults(),
        )
        validated = ResolvedRuntime(
            ctx,
            ConfigLoadResult(ConfigStatus.ABSENT, {}, ()),
            JournalLoadResult(JournalLoadStatus.ABSENT, None),
            build_runtime_identity(ctx),
        )
        source = inspect.getsource(sync_run_for)
        self.assertNotIn("build_resolved_runtime", source)
        run = sync_run_for(validated)
        self.assertIs(run.context, ctx)

    def test_cli_command_modules_do_not_construct_runtime_resolver(self):
        for path in _COMMAND_MODULES:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Name) and func.id == "RuntimeResolver":
                        self.fail(f"{path.name} must not construct RuntimeResolver()")
                    if isinstance(func, ast.Call) and isinstance(func.func, ast.Name):
                        if func.func.id == "RuntimeResolver":
                            self.fail(f"{path.name} must not construct RuntimeResolver()")

    def test_runtime_resolver_builds_explicit_runtime(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            resolved = RuntimeResolver().resolve_read(ProjectRef(wordlist=wordlist))
            self.assertIsInstance(resolved, ResolvedRuntime)
            self.assertEqual(resolved.context.wordlist, wordlist)

    def test_mutation_scope_module_always_acquires_lock(self):
        from spell_sync.application import mutation_scope as mutation_scope_mod

        source = inspect.getsource(mutation_scope_mod.mutation_scope_for)
        self.assertNotIn("if bound is not None", source)
        self.assertNotIn("yield bound", source)

    def test_no_reload_parameter_in_load_config_result(self):
        signature = inspect.signature(settings_mod.load_config_result)
        self.assertNotIn("reload", signature.parameters)

    def test_write_rendered_requires_explicit_settings(self):
        from spell_sync.push_prepared import write_rendered

        signature = inspect.signature(write_rendered)
        self.assertIn("settings", signature.parameters)
        self.assertEqual(
            signature.parameters["settings"].kind,
            inspect.Parameter.KEYWORD_ONLY,
        )
