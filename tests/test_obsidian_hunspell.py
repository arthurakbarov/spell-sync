#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Obsidian and Hunspell dictionary I/O, paths, and push guards."""

from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from conftest import DEFAULT_OPTS

import spell_sync.app_process_check as obsidian_guard
import spell_sync.commands as commands
import spell_sync.dictionaries as dict_mod
import spell_sync.io as io_mod
import spell_sync.paths as paths_mod
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.io import read_text_words, write_text_words
from spell_sync.sync_run import SyncRun


class TestHunspellIo(unittest.TestCase):
    def test_read_hunspell_skips_comments(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "personal.dic"
            path.write_text("# header\nalpha\n# trailing\nbeta\n", encoding="utf-8")
            words = io_mod.read_hunspell_words(path, quiet=True)
            self.assertEqual(words, {"alpha", "beta"})

    def test_read_hunspell_strips_affix_and_prohibited(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "personal.dic"
            path.write_text(
                "3\nalpha/MS\n*prohibited\n# comment\nbeta\n",
                encoding="utf-8",
            )
            words = io_mod.read_hunspell_words(path, quiet=True)
            self.assertEqual(words, {"alpha", "beta"})
            self.assertTrue(
                io_mod.write_hunspell_words(path, ["alpha", "beta", "gamma"], quiet=True)
            )
            self.assertEqual(path.read_text(encoding="utf-8"), "alpha/MS\nbeta\ngamma\n")

    def test_read_hunspell_skips_count_header_only(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "personal.dic"
            path.write_text("2\nonly\n", encoding="utf-8")
            self.assertEqual(io_mod.read_hunspell_words(path, quiet=True), {"only"})

    def test_read_hunspell_corrupt_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "personal.dic"
            path.write_bytes(b"\xff\xfe\xfd")
            self.assertEqual(io_mod.read_hunspell_words(path, quiet=True), set())

    def test_read_hunspell_corrupt_logs_when_not_quiet(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "personal.dic"
            path.write_bytes(b"\xff\xfe\xfd")
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(io_mod.read_hunspell_words(path, quiet=False), set())
            self.assertIn("read failed (hunspell)", buf.getvalue())

    def test_read_hunspell_missing_file_returns_empty(self):
        self.assertEqual(io_mod.read_hunspell_words("/no/such.dic", quiet=True), set())

    def test_read_hunspell_skips_blank_affix_lines(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "personal.dic"
            path.write_text("   /MS\n\ufeff\nalpha\n", encoding="utf-8")
            self.assertEqual(io_mod.read_hunspell_words(path, quiet=True), {"alpha"})

    def test_read_hunspell_success_logs_when_not_quiet(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "personal.dic"
            path.write_text("alpha\n", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                words = io_mod.read_hunspell_words(path, quiet=False)
            self.assertEqual(words, {"alpha"})
            self.assertIn("[read ]", buf.getvalue())

    def test_write_hunspell_overwrites_corrupt_existing_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "personal.dic"
            path.write_bytes(b"\xff\xfe\xfd")
            self.assertTrue(io_mod.write_hunspell_words(path, ["alpha"], quiet=True))
            self.assertEqual(io_mod.read_hunspell_words(path, quiet=True), {"alpha"})

    def test_write_hunspell_overwrites_corrupt_logs_when_not_quiet(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "personal.dic"
            path.write_bytes(b"\xff\xfe\xfd")
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertTrue(io_mod.write_hunspell_words(path, ["alpha"], quiet=False))
            # At least one warning should be emitted while reading corrupt content.
            self.assertTrue(buf.getvalue())

    def test_write_hunspell_failure_logs_when_not_quiet(self):
        with patch.object(io_mod, "atomic_write", side_effect=OSError("fail")):
            buf = io.StringIO()
            with redirect_stdout(buf):
                ok = io_mod.write_hunspell_words("/x/custom.dic", ["a"], quiet=False)
            self.assertFalse(ok)
            self.assertIn("no write access", buf.getvalue())

    def test_write_hunspell_success_logs_when_not_quiet(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "personal.dic"
            buf = io.StringIO()
            with redirect_stdout(buf):
                ok = io_mod.write_hunspell_words(path, ["alpha"], quiet=False)
            self.assertTrue(ok)
            self.assertIn("[write]", buf.getvalue())

    def test_pull_ignores_corrupt_hunspell_dictionary(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            good = Path(d) / "good.dic"
            corrupt = Path(d) / "bad.dic"
            write_text_words(str(wordlist), ["alpha"], "utf-8", False, quiet=True)
            good.write_text("beta\n", encoding="utf-8")
            corrupt.write_bytes(b"\xff\xfe\xfd")
            run = SyncRun(
                wordlist=str(wordlist),
                dictionaries=[
                    Dictionary(
                        "hunspell:good",
                        str(good),
                        DictionaryFormat.HUNSPELL,
                    ),
                    Dictionary(
                        "hunspell:bad",
                        str(corrupt),
                        DictionaryFormat.HUNSPELL,
                    ),
                ],
            )
            from spell_sync.read_outcome import (
                DictionaryReadResult,
                ReadStatus,
                dictionary_read_result,
            )

            real = dictionary_read_result

            def mock_read(dictionary):
                if "bad" in dictionary.path:
                    return DictionaryReadResult(ReadStatus.CORRUPT, frozenset(), "corrupt", None)
                return real(dictionary)

            with patch("spell_sync.push_setup.dictionary_read_result", mock_read):
                before, after = run.pull_into_wordlist()
            self.assertEqual((before, after), (1, 2))
            self.assertEqual(read_text_words(str(wordlist), quiet=True), {"alpha", "beta"})
            self.assertEqual(corrupt.read_bytes(), b"\xff\xfe\xfd")

    def test_push_overwrites_corrupt_hunspell_dictionary(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            good = Path(d) / "good.dic"
            corrupt = Path(d) / "custom.dic"
            write_text_words(str(wordlist), ["alpha"], "utf-8", False, quiet=True)
            good.write_text("local\n", encoding="utf-8")
            corrupt.write_bytes(b"\xff\xfe\xfd")
            run = SyncRun(
                wordlist=str(wordlist),
                dictionaries=[
                    Dictionary(
                        "hunspell:good",
                        str(good),
                        DictionaryFormat.HUNSPELL,
                    ),
                    Dictionary(
                        "hunspell:custom",
                        str(corrupt),
                        DictionaryFormat.HUNSPELL,
                    ),
                ],
            )
            result = run.push_from_wordlist()
            self.assertEqual(result.skipped, ())
            self.assertEqual(set(result.written), {"hunspell:good", "hunspell:custom"})
            self.assertEqual(io_mod.read_hunspell_words(good, quiet=True), {"alpha"})
            self.assertEqual(io_mod.read_hunspell_words(corrupt, quiet=True), {"alpha"})

    def test_write_hunspell_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "personal.dic"
            self.assertTrue(io_mod.write_hunspell_words(path, ["zebra", "alpha"], quiet=True))
            self.assertEqual(io_mod.read_hunspell_words(path, quiet=True), {"alpha", "zebra"})
            self.assertEqual(path.read_text(encoding="utf-8"), "alpha\nzebra\n")

    def test_write_hunspell_refreshes_affix_after_external_edit(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "personal.dic"
            path.write_text("alpha/MS\n", encoding="utf-8")
            io_mod.read_hunspell_words(path, quiet=True)
            path.write_text("alpha\nbeta/XY\n", encoding="utf-8")
            self.assertTrue(io_mod.write_hunspell_words(path, ["alpha", "beta"], quiet=True))
            self.assertEqual(path.read_text(encoding="utf-8"), "alpha\nbeta/XY\n")

    def test_dictionary_hunspell_format(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "custom.dic"
            dictionary = Dictionary(
                "hunspell:custom",
                str(path),
                DictionaryFormat.HUNSPELL,
            )
            self.assertTrue(dictionary.write({"one", "two"}, quiet=True))
            self.assertEqual(dictionary.read(quiet=True), {"one", "two"})


class TestHunspellPaths(unittest.TestCase):
    def test_hunspell_dict_paths_fixed_files(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            default = home / ".hunspell_default"
            default.write_text("word\n", encoding="utf-8")
            with patch("spell_sync.paths.home_dir", return_value=home):
                with patch("spell_sync.paths.is_macos", return_value=False):
                    with patch("spell_sync.paths.is_windows", return_value=False):
                        pairs = paths_mod.hunspell_dict_paths()
            self.assertEqual(pairs, [("default", default)])

    def test_hunspell_dict_paths_config_dir(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            config_dir = home / ".config" / "hunspell"
            config_dir.mkdir(parents=True)
            extra = config_dir / "work.dic"
            extra.write_text("x\n", encoding="utf-8")
            with patch("spell_sync.paths.home_dir", return_value=home):
                with patch("spell_sync.paths.is_macos", return_value=False):
                    with patch("spell_sync.paths.is_windows", return_value=False):
                        pairs = paths_mod.hunspell_dict_paths()
            self.assertEqual(pairs, [("work.dic", extra)])

    def test_hunspell_dict_paths_macos_local(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            local = home / "Library" / "Spelling" / "local"
            local.parent.mkdir(parents=True)
            local.write_text("mac\n", encoding="utf-8")
            with patch("spell_sync.paths.home_dir", return_value=home):
                with patch("spell_sync.paths.is_macos", return_value=True):
                    with patch("spell_sync.paths.is_windows", return_value=False):
                        pairs = paths_mod.hunspell_dict_paths()
            labels = [label for label, _ in pairs]
            self.assertIn("local", labels)

    def test_discover_includes_hunspell_when_enabled(self):
        with tempfile.TemporaryDirectory() as d:
            dic = Path(d) / ".hunspell_default"
            dic.write_text("alpha\n", encoding="utf-8")
            with (
                patch("spell_sync.dictionaries.enable_hunspell", return_value=True),
                patch("spell_sync.dictionaries.hunspell_dict_paths") as mock_paths,
            ):
                mock_paths.return_value = [("default", dic)]
                with patch("spell_sync.dictionaries.is_windows", return_value=False):
                    with patch("spell_sync.dictionaries.is_macos", return_value=False):
                        with patch(
                            "spell_sync.dictionaries.sublime_packages_dir",
                            return_value=Path(d) / "Packages",
                        ):
                            found = [
                                item.name
                                for item in dict_mod.discover_dictionaries()
                                if item.name.startswith("hunspell:")
                            ]
            self.assertEqual(found, ["hunspell:default"])


class TestObsidianPaths(unittest.TestCase):
    def test_obsidian_dict_path_macos(self):
        with patch("spell_sync.paths.is_macos", return_value=True):
            with patch("spell_sync.paths.is_windows", return_value=False):
                path = paths_mod.obsidian_dict_path()
                self.assertIn("obsidian", str(path))
                self.assertIn("Custom Dictionary.txt", str(path))
                self.assertIn("Application Support", str(path))

    def test_obsidian_dict_paths_when_dir_exists(self):
        with tempfile.TemporaryDirectory() as d:
            obs_dir = Path(d) / "obsidian"
            obs_dir.mkdir()
            custom_path = obs_dir / "Custom Dictionary.txt"
            with patch("spell_sync.paths.obsidian_dict_path", return_value=custom_path):
                pairs = paths_mod.obsidian_dict_paths()
            self.assertEqual(pairs, [("obsidian", custom_path)])

    def test_obsidian_dict_paths_missing(self):
        with patch("spell_sync.paths.obsidian_dict_path") as mock_path:
            mock_path.return_value = Path("/no/obsidian/Custom Dictionary.txt")
            self.assertEqual(paths_mod.obsidian_dict_paths(), [])

    def test_discover_includes_obsidian_when_enabled(self):
        with tempfile.TemporaryDirectory() as d:
            obs_dir = Path(d) / "obsidian"
            obs_dir.mkdir()
            custom = obs_dir / "Custom Dictionary.txt"
            with (
                patch("spell_sync.dictionaries.enable_obsidian", return_value=True),
                patch("spell_sync.dictionaries.obsidian_dict_paths") as mock_paths,
            ):
                mock_paths.return_value = [("obsidian", custom)]
                with patch("spell_sync.dictionaries.is_windows", return_value=False):
                    with patch("spell_sync.dictionaries.is_macos", return_value=False):
                        with patch(
                            "spell_sync.dictionaries.sublime_packages_dir",
                            return_value=Path(d) / "Packages",
                        ):
                            found = [
                                item.name
                                for item in dict_mod.discover_dictionaries()
                                if item.name == "obsidian"
                            ]
            self.assertEqual(found, ["obsidian"])


class TestObsidianIo(unittest.TestCase):
    def test_obsidian_uses_chrome_format(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "Custom Dictionary.txt"
            dictionary = Dictionary(
                "obsidian",
                str(path),
                DictionaryFormat.CHROME,
            )
            self.assertTrue(dictionary.write({"beta", "alpha"}, quiet=True))
            text = path.read_text(encoding="utf-8")
            self.assertIn("checksum_v1", text)
            body = "alpha\nbeta\n"
            expected = hashlib.md5(body.encode("utf-8")).hexdigest()
            self.assertTrue(text.endswith(f"checksum_v1 = {expected}"))
            self.assertEqual(dictionary.read(quiet=True), {"alpha", "beta"})


class TestObsidianCheck(unittest.TestCase):
    def test_skips_when_obsidian_disabled(self):
        with patch.object(obsidian_guard, "obsidian_dictionaries_enabled", return_value=False):
            self.assertTrue(obsidian_guard.confirm_obsidian_before_push(interactive=True))

    def test_non_interactive_warns_when_running(self):
        with (
            patch.object(obsidian_guard, "obsidian_dictionaries_enabled", return_value=True),
            patch.object(obsidian_guard, "is_obsidian_running", return_value=True),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertTrue(obsidian_guard.confirm_obsidian_before_push(interactive=False))
            self.assertIn("Obsidian is running", buf.getvalue())

    def test_push_check_runs_obsidian_guard(self):
        with (
            patch.object(commands, "confirm_chrome_before_push", return_value=True),
            patch.object(commands, "confirm_firefox_before_push", return_value=True),
            patch.object(commands, "confirm_obsidian_before_push", return_value=False),
        ):
            self.assertFalse(commands._running_apps_check_for_push(DEFAULT_OPTS))

    def test_is_obsidian_running_macos(self):
        fake = type("R", (), {"returncode": 0})()
        with patch.object(obsidian_guard.subprocess, "run", return_value=fake):
            self.assertTrue(obsidian_guard._macos_pgrep_exact("Obsidian"))

    def test_windows_exe_running_obsidian(self):
        fake = type("R", (), {"returncode": 0, "stdout": "Obsidian.exe 1234"})()
        with patch.object(obsidian_guard.subprocess, "run", return_value=fake):
            self.assertTrue(obsidian_guard._windows_exe_running("Obsidian.exe"))

    def test_obsidian_dictionaries_disabled_without_paths(self):
        with (
            patch("spell_sync.config.enable_obsidian", return_value=True),
            patch.object(obsidian_guard, "obsidian_dict_paths", return_value=[]),
        ):
            self.assertFalse(obsidian_guard.obsidian_dictionaries_enabled())

    def test_interactive_cancel(self):
        with (
            patch.object(obsidian_guard, "obsidian_dictionaries_enabled", return_value=True),
            patch.object(obsidian_guard, "is_obsidian_running", return_value=True),
            patch("builtins.input", return_value="n"),
        ):
            self.assertFalse(obsidian_guard.confirm_obsidian_before_push(interactive=True))

    def test_unknown_state_non_interactive(self):
        with (
            patch.object(obsidian_guard, "obsidian_dictionaries_enabled", return_value=True),
            patch.object(obsidian_guard, "is_obsidian_running", return_value=None),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertTrue(obsidian_guard.confirm_obsidian_before_push(interactive=False))
            self.assertIn("Could not check", buf.getvalue())

    def test_is_obsidian_running_linux(self):
        fake = type("R", (), {"returncode": 0})()
        with (
            patch.object(obsidian_guard, "is_windows", return_value=False),
            patch.object(obsidian_guard.sys, "platform", "linux"),
            patch.object(obsidian_guard.subprocess, "run", return_value=fake),
        ):
            self.assertTrue(obsidian_guard.is_obsidian_running())

    def test_is_obsidian_running_macos_dispatch(self):
        with (
            patch.object(obsidian_guard, "is_windows", return_value=False),
            patch.object(obsidian_guard.sys, "platform", "darwin"),
            patch.object(obsidian_guard, "_macos_pgrep_exact", return_value=False) as mac,
        ):
            self.assertFalse(obsidian_guard.is_obsidian_running())
            mac.assert_called_once_with("Obsidian")

    def test_is_obsidian_running_windows(self):
        with (
            patch.object(obsidian_guard, "is_windows", return_value=True),
            patch.object(obsidian_guard, "_windows_exe_running", return_value=True) as win,
        ):
            self.assertTrue(obsidian_guard.is_obsidian_running())
            win.assert_called_once_with("Obsidian.exe")

    def test_pgrep_running_interpretation(self):
        self.assertTrue(obsidian_guard._pgrep_running(0))
        self.assertFalse(obsidian_guard._pgrep_running(1))
        self.assertIsNone(obsidian_guard._pgrep_running(2))

    def test_hunspell_config_dir_os_error(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            config_dir = home / ".config" / "hunspell"
            config_dir.mkdir(parents=True)
            with patch("spell_sync.paths.home_dir", return_value=home):
                with patch("spell_sync.paths.is_macos", return_value=False):
                    with patch("spell_sync.paths.is_windows", return_value=False):
                        with patch.object(Path, "iterdir", side_effect=OSError("denied")):
                            self.assertEqual(paths_mod.hunspell_dict_paths(), [])


class TestPullPushIntegration(unittest.TestCase):
    def test_hunspell_import_push_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            dic = Path(d) / "custom.dic"
            dic.write_text("local\n", encoding="utf-8")
            dictionary = Dictionary(
                "hunspell:custom",
                str(dic),
                DictionaryFormat.HUNSPELL,
            )
            run = SyncRun(wordlist=str(wordlist), dictionaries=[dictionary])
            before, after = run.pull_into_wordlist()
            self.assertEqual((before, after), (0, 1))
            write_text_words(str(wordlist), ["alpha", "local"], "utf-8", False, quiet=True)
            with (
                patch.object(commands, "_running_apps_check_for_push", return_value=True),
                patch.object(commands, "sync_run_for", return_value=run),
            ):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(commands.cmd_push(DEFAULT_OPTS), 0)
            self.assertEqual(io_mod.read_hunspell_words(dic, quiet=True), {"alpha", "local"})


if __name__ == "__main__":
    unittest.main()
