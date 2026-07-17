#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Public API and naming consistency."""

import importlib
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import spell_sync
import spell_sync.commands as commands
from spell_sync.cli_options import CliOptions
from spell_sync.dictionaries import Dictionary, DictionaryFormat, discover_dictionaries
from spell_sync.exit_codes import ExitCode
from spell_sync.io import write_text_words
from spell_sync.paths import project_root, wordlist_path
from spell_sync.sync_run import SyncRun


class TestModuleLayout(unittest.TestCase):
    def test_all_package_modules_importable(self):
        pkg_dir = Path(spell_sync.__file__).resolve().parent
        names = sorted(path.stem for path in pkg_dir.glob("*.py") if not path.name.startswith("_"))
        self.assertGreater(len(names), 20)
        for name in names:
            with self.subTest(module=name):
                importlib.import_module(f"spell_sync.{name}")


class TestPublicExports(unittest.TestCase):
    def test_wordlist_path_points_to_wordlist_txt(self):
        path = wordlist_path()
        self.assertEqual(path.name, "wordlist.txt")
        self.assertTrue(path.is_absolute() or path.is_file() or path.parent.exists())

    def test_project_root_prefers_cwd_when_not_in_dev_clone(self):
        with tempfile.TemporaryDirectory() as d:
            fake_site = os.path.join(d, "site-packages")
            os.makedirs(fake_site)
            with patch("spell_sync.paths.REPO_DIR", Path(fake_site)):
                with patch("spell_sync.paths._is_spell_sync_project", return_value=False):
                    with patch("spell_sync.paths.Path.cwd", return_value=Path(d)):
                        self.assertEqual(project_root(), Path(d))
                        self.assertEqual(wordlist_path(), Path(d) / "wordlist.txt")

    def test_project_root_walks_up_to_clone_root(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            sub = root / "notes"
            sub.mkdir()
            (root / "pyproject.toml").write_text(
                '[project]\nname = "spell-sync"\n', encoding="utf-8"
            )
            (root / "spell_sync").mkdir()
            with patch("spell_sync.paths.Path.cwd", return_value=sub):
                self.assertEqual(project_root(), root)
                self.assertEqual(wordlist_path(), root / "wordlist.txt")

    def test_project_root_pyproject_requires_spell_sync_package(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            sub = root / "notes"
            sub.mkdir()
            (root / "pyproject.toml").write_text(
                '[project]\nname = "spell-sync"\n', encoding="utf-8"
            )
            fake_repo = Path("/nonexistent/spell-sync")
            with (
                patch("spell_sync.paths.REPO_DIR", fake_repo),
                patch("spell_sync.paths.Path.cwd", return_value=sub),
            ):
                self.assertEqual(project_root(), sub)

    def test_project_root_unreadable_pyproject_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            sub = root / "notes"
            sub.mkdir()
            (root / "spell_sync").mkdir()
            (root / "pyproject.toml").write_text(
                '[project]\nname = "spell-sync"\n', encoding="utf-8"
            )
            original_read_text = Path.read_text

            def picky_read(self, *args, **kwargs):
                if self.name == "pyproject.toml":
                    raise OSError("denied")
                return original_read_text(self, *args, **kwargs)

            fake_repo = Path("/nonexistent/spell-sync")
            with (
                patch("spell_sync.paths.REPO_DIR", fake_repo),
                patch("spell_sync.paths.Path.cwd", return_value=sub),
                patch.object(Path, "read_text", picky_read),
            ):
                self.assertEqual(project_root(), sub)

    def test_discover_dictionaries_returns_dictionary_instances(self):
        with (
            patch("spell_sync.dictionaries.enable_chrome", return_value=False),
            patch("spell_sync.dictionaries.enable_editors", return_value=False),
            patch("spell_sync.dictionaries.is_windows", return_value=False),
            patch("spell_sync.dictionaries.is_macos", return_value=False),
        ):
            items = discover_dictionaries()
        self.assertIsInstance(items, list)
        for item in items:
            self.assertIsInstance(item, Dictionary)

    def test_exit_code_wordlist_unreadable(self):
        self.assertEqual(int(ExitCode.WORDLIST_UNREADABLE), 6)

    def test_init_all_exports_are_attributes(self):
        for name in spell_sync.__all__:
            with self.subTest(export=name):
                self.assertTrue(hasattr(spell_sync, name))

    def test_version_matches_pyproject_in_repo(self):
        from spell_sync.paths import REPO_DIR
        from spell_sync.runtime import read_pyproject_version

        expected = read_pyproject_version(REPO_DIR / "pyproject.toml")
        self.assertEqual(expected, "0.1.0")


class TestJsonNaming(unittest.TestCase):
    def test_status_json_schema(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = os.path.join(d, "wordlist.txt")
            dict_path = os.path.join(d, "a.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(dict_path, ["alpha"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[
                    Dictionary("a", dict_path, DictionaryFormat.TEXT),
                ],
            )
            with patch.object(commands, "sync_run_for", return_value=run):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = commands.cmd_status(CliOptions(json_output=True))
                self.assertEqual(code, 0)
                payload = json.loads(buf.getvalue())
                self.assertIn("wordlist_count", payload)
                self.assertIn("version", payload)
                self.assertIn("skipped_unreadable", payload)
                self.assertIn("dictionaries", payload)
                self.assertNotIn("master_count", payload)
                self.assertNotIn("stores", payload)
                diff = payload["dictionaries"][0]
                self.assertIn("local_count", diff)
                self.assertNotIn("store_count", diff)


if __name__ == "__main__":
    unittest.main(verbosity=2)
