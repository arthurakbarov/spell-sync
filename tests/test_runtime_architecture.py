#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Runtime architecture: settings cache, dictionary registry, sync context."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import spell_sync.settings as settings_mod
from spell_sync.cli_options import CliOptions
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.dictionary_registry import DictionarySource, discover_from_sources
from spell_sync.sync_context import RuntimeContext
from spell_sync.sync_run import SyncRun, sync_run_for


class TestSettingsCache(unittest.TestCase):
    def setUp(self) -> None:
        settings_mod.clear_settings_cache()

    def tearDown(self) -> None:
        settings_mod.clear_settings_cache()

    def test_load_user_settings_is_cached(self):
        with tempfile.TemporaryDirectory() as d:
            project = Path(d) / "spell-sync.toml"
            project.write_text("[dictionaries]\nchrome = true\n", encoding="utf-8")
            with patch.object(settings_mod, "config_paths", return_value=[project]):
                first = settings_mod.load_user_settings()
                project.write_text("[dictionaries]\nchrome = false\n", encoding="utf-8")
                second = settings_mod.load_user_settings()
            self.assertTrue(first["dictionaries"]["chrome"])
            self.assertTrue(second["dictionaries"]["chrome"])

    def test_reload_clears_cache(self):
        with tempfile.TemporaryDirectory() as d:
            project = Path(d) / "spell-sync.toml"
            project.write_text("[dictionaries]\nchrome = true\n", encoding="utf-8")
            with patch.object(settings_mod, "config_paths", return_value=[project]):
                settings_mod.load_user_settings()
                project.write_text("[dictionaries]\nchrome = false\n", encoding="utf-8")
                reloaded = settings_mod.load_user_settings(reload=True)
            self.assertFalse(reloaded["dictionaries"]["chrome"])

    def test_clear_settings_cache(self):
        with tempfile.TemporaryDirectory() as d:
            project = Path(d) / "spell-sync.toml"
            project.write_text("[dictionaries]\nchrome = true\n", encoding="utf-8")
            with patch.object(settings_mod, "config_paths", return_value=[project]):
                settings_mod.load_user_settings_with_issues()
                settings_mod.clear_settings_cache()
                project.write_text("[dictionaries]\nchrome = false\n", encoding="utf-8")
                settings, _issues = settings_mod.load_user_settings_with_issues()
            self.assertFalse(settings["dictionaries"]["chrome"])


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
                strict_push=True,
            )
            self.assertEqual(ctx.wordlist_file, wordlist)
            self.assertEqual(ctx.dictionaries, tuple(dictionaries))
            self.assertTrue(ctx.strict_push)
            self.assertEqual(ctx.dictionary_names(), ("a",))

    def test_sync_run_exposes_strict_push(self):
        ctx = RuntimeContext.build(strict_push=True)
        run = SyncRun(context=ctx)
        self.assertTrue(run.strict_push)

    def test_sync_run_wraps_context(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dict_path = Path(d) / "a.txt"
            ctx = RuntimeContext.build(
                wordlist=wordlist,
                dictionaries=[Dictionary("a", dict_path, DictionaryFormat.TEXT)],
            )
            run = SyncRun(context=ctx)
            self.assertIs(run.context, ctx)
            self.assertEqual(run.wordlist_file, wordlist)
            self.assertEqual(run.dictionaries[0].name, "a")

    def test_sync_run_for_uses_cli_wordlist(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            wordlist = f.name
        try:
            opts = CliOptions(wordlist=wordlist)
            run = sync_run_for(opts)
            self.assertEqual(str(run.wordlist_file), wordlist)
        finally:
            Path(wordlist).unlink(missing_ok=True)
