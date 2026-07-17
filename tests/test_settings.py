#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""spell-sync.toml and exit code tests."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import spell_sync.settings as settings_mod
from spell_sync.exit_codes import ExitCode


class TestExitCodes(unittest.TestCase):
    def test_distinct_codes(self):
        self.assertEqual(int(ExitCode.OK), 0)
        self.assertEqual(int(ExitCode.PUSH_ABORT), 1)
        self.assertEqual(int(ExitCode.LINT_FAILED), 2)
        self.assertEqual(int(ExitCode.UNKNOWN_COMMAND), 3)
        self.assertEqual(int(ExitCode.CANCELLED), 4)
        self.assertEqual(int(ExitCode.PARTIAL_PUSH), 5)
        self.assertEqual(int(ExitCode.WORDLIST_UNREADABLE), 6)
        self.assertEqual(int(ExitCode.SYNC_INTERRUPTED), 130)
        self.assertNotEqual(ExitCode.PUSH_ABORT, ExitCode.LINT_FAILED)


class TestUserSettings(unittest.TestCase):
    def test_parse_simple_toml(self):
        content = "[dictionaries]\neditors = false\nchrome = true\n"
        with tempfile.NamedTemporaryFile(
            "w",
            suffix=".toml",
            delete=False,
            encoding="utf-8",
        ) as handle:
            handle.write(content)
            path = handle.name
        try:
            parsed = settings_mod._parse_toml(Path(path))
            self.assertFalse(parsed["dictionaries"]["editors"])
            self.assertTrue(parsed["dictionaries"]["chrome"])
        finally:
            os.unlink(path)

    def test_dictionary_flag_default(self):
        self.assertTrue(settings_mod.dictionary_flag({}, "editors", True))
        settings = {"dictionaries": {"chrome": False}}
        self.assertFalse(settings_mod.dictionary_flag(settings, "chrome", True))

    def test_push_max_removals_explicit_config(self):
        import spell_sync.config as config_mod

        with patch.object(
            settings_mod,
            "load_user_settings",
            return_value={"push": {"max_removals_without_confirm": 99}},
        ):
            self.assertEqual(config_mod.push_max_removals_without_confirm(), 99)

    def test_push_and_backup_defaults(self):
        import spell_sync.config as config_mod

        with patch.object(settings_mod, "load_user_settings", return_value={}):
            self.assertEqual(
                config_mod.push_max_removals_without_confirm(),
                config_mod.PUSH_MAX_REMOVALS_WITHOUT_CONFIRM_DEFAULT,
            )
            self.assertEqual(config_mod.backup_keep_count(), config_mod.BACKUP_KEEP_DEFAULT)

    def test_project_config_overrides_home(self):
        with tempfile.TemporaryDirectory() as d:
            repo_cfg = Path(d) / "repo.toml"
            home_cfg = Path(d) / "home.toml"
            repo_cfg.write_text("[dictionaries]\nchrome = false\n", encoding="utf-8")
            home_cfg.write_text("[dictionaries]\nchrome = true\n", encoding="utf-8")
            with patch.object(settings_mod, "config_paths", return_value=[home_cfg, repo_cfg]):
                merged = settings_mod.load_user_settings()
            self.assertFalse(merged["dictionaries"]["chrome"])


class TestSettingsParsingEdgeCases(unittest.TestCase):
    def test_parse_toml_root_scalar_keeps_tables_with_issue(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spell-sync.toml"
            path.write_text("orphan = true\n[dictionaries]\nchrome = true\n", encoding="utf-8")
            data, issues = settings_mod._parse_toml_with_issues(path)
            self.assertTrue(data["dictionaries"]["chrome"])
            self.assertTrue(any("must be a table" in i for i in issues))

    def test_parse_toml_rejects_yes(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spell-sync.toml"
            path.write_text("[dictionaries]\nchrome = yes\n", encoding="utf-8")
            data, issues = settings_mod._parse_toml_with_issues(path)
            self.assertEqual(data, {})
            self.assertTrue(issues)

    def test_parse_toml_strips_inline_comment(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spell-sync.toml"
            path.write_text("[dictionaries]\nchrome = true # enabled\n", encoding="utf-8")
            data = settings_mod._parse_toml(path)
            self.assertTrue(data["dictionaries"]["chrome"])

    def test_parse_toml_rejects_malformed(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spell-sync.toml"
            path.write_text(
                "# comment\nnot a section\n[dictionaries]\nchrome = true\n",
                encoding="utf-8",
            )
            data, issues = settings_mod._parse_toml_with_issues(path)
            self.assertEqual(data, {})
            self.assertTrue(issues)

    def test_parse_toml_rejects_yes_boolean_alias(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spell-sync.toml"
            path.write_text("[dictionaries]\nchrome = yes\n", encoding="utf-8")
            data, issues = settings_mod._parse_toml_with_issues(path)
            self.assertEqual(data, {})
            self.assertTrue(issues)

    def test_load_user_settings_merges_files(self):
        with tempfile.TemporaryDirectory() as d:
            repo_cfg = Path(d) / "repo.toml"
            home_cfg = Path(d) / "home.toml"
            repo_cfg.write_text("[dictionaries]\neditors = false\n", encoding="utf-8")
            home_cfg.write_text("[dictionaries]\nchrome = false\n", encoding="utf-8")
            with patch.object(settings_mod, "config_paths", return_value=[home_cfg, repo_cfg]):
                merged = settings_mod.load_user_settings()
            self.assertFalse(merged["dictionaries"]["editors"])
            self.assertFalse(merged["dictionaries"]["chrome"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
