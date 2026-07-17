#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests: words, IO, lint, dictionaries, paths."""

import hashlib
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.io import (
    read_json_words,
    read_text_words,
    write_chrome_words,
    write_json_words,
    write_text_words,
)
from spell_sync.lint import analyze_words
from spell_sync.paths import editor_dict_paths
from spell_sync.words import (
    has_cyrillic,
    has_latin,
    is_hard_junk,
    sort_words,
    subset_english,
    subset_russian,
)


class TestWords(unittest.TestCase):
    def test_has_cyrillic_latin(self):
        self.assertTrue(has_cyrillic("слово"))
        self.assertFalse(has_cyrillic("word"))
        self.assertTrue(has_latin("word"))
        both = has_cyrillic("прокcи") and has_latin("прокcи")
        self.assertTrue(both)

    def test_hard_junk(self):
        self.assertTrue(is_hard_junk(""))
        self.assertTrue(is_hard_junk("two words"))
        self.assertTrue(is_hard_junk("---"))
        self.assertFalse(is_hard_junk("os"))

    def test_normalize_token_none_and_bom(self):
        import spell_sync.words as words_mod

        self.assertEqual(words_mod.normalize_token(None), "")
        self.assertEqual(words_mod.normalize_token("\ufeffword"), "word")

    def test_hard_junk_control_chars(self):
        import spell_sync.words as words_mod

        self.assertTrue(words_mod.is_hard_junk("a\x01b"))

    def test_clean_and_sort(self):
        words = ["Яндекс", "  os ", "bad word", "os", ""]
        self.assertEqual(sort_words(words), ["os", "Яндекс"])

    def test_language_subsets(self):
        words = {"робастный", "backend", "прокcи", "π", "1080p"}
        self.assertIn("backend", subset_english(words))
        self.assertNotIn("backend", subset_russian(words))
        overlap = subset_russian(words) & subset_english(words)
        self.assertIn("прокcи", overlap)


class TestDictionary(unittest.TestCase):
    def test_target_words_with_subset(self):
        dictionary = Dictionary(
            "win-ru",
            "/tmp/x",
            DictionaryFormat.TEXT,
            subset=subset_russian,
        )
        target = dictionary.target_words({"робастный", "backend", "π"})
        self.assertEqual(target, {"робастный", "π"})


class TestIO(unittest.TestCase):
    def test_text_roundtrip_utf8(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "dict.txt")
            write_text_words(p, ["Яндекс", "os"], "utf-8", False, quiet=True)
            self.assertEqual(read_text_words(p, quiet=True), {"Яндекс", "os"})

    def test_windows_dic_roundtrip_utf16le_bom(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "default.dic")
            words = ["робастный", "backend"]
            write_text_words(p, words, "utf-16-le", True, quiet=True)
            with open(p, "rb") as fh:
                self.assertEqual(fh.read(2), b"\xff\xfe")

    def test_json_and_chrome_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            jp = os.path.join(d, "prefs.json")
            cp = os.path.join(d, "Custom Dictionary.txt")
            write_json_words(jp, ["os"], quiet=True)
            write_chrome_words(cp, ["os"], quiet=True)
            self.assertEqual(read_json_words(jp, quiet=True), {"os"})
            with open(cp, encoding="utf-8") as fh:
                raw = fh.read()
            pos = raw.rfind("checksum_v1 = ")
            body, cs = raw[:pos], raw[pos + len("checksum_v1 = ") :].strip()
            self.assertEqual(hashlib.md5(body.encode()).hexdigest(), cs)

    def test_text_read_permission_denied(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "dict.txt")
            write_text_words(p, ["alpha"], "utf-8", False, quiet=True)
            side_effect = PermissionError(1, "Operation not permitted")
            with patch("spell_sync.io.open", side_effect=side_effect):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    words = read_text_words(p, quiet=False)
                self.assertEqual(words, set())
                self.assertIn("read failed (text)", buf.getvalue())


class TestLint(unittest.TestCase):
    def test_report_and_whitelist(self):
        import spell_sync.lint as lint_mod

        rep = analyze_words(
            ["Jupyter", "jupyter", "прокcи", "xy"],
        ).as_dict()
        self.assertTrue(rep["case_dupes"])
        self.assertIn("прокcи", rep["homoglyphs"])
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "lint-whitelist.txt").write_text("cafе\nos\n", encoding="utf-8")
            lint_mod._whitelist_cache = None
            with patch.object(lint_mod, "project_root", return_value=root):
                clean = analyze_words(["cafе", "os"]).as_dict()
        self.assertEqual(clean["homoglyphs"], [])
        self.assertEqual(clean["very_short"], [])


class TestCspellPaths(unittest.TestCase):
    def test_returns_at_least_one_path(self):
        paths = editor_dict_paths()
        self.assertGreaterEqual(len(paths), 1)


class TestMacosPaths(unittest.TestCase):
    def test_includes_classic_and_group_when_container_exists(self):
        import sys

        if sys.platform != "darwin":
            self.skipTest("macOS only")
        from spell_sync.paths import home_dir, macos_dictionary_paths

        paths = macos_dictionary_paths()
        names = [name for name, _ in paths]
        self.assertIn("macos", names)
        group = (
            home_dir()
            / "Library"
            / "Group Containers"
            / "group.com.apple.AppleSpell"
            / "Library"
            / "Spelling"
        )
        if group.is_dir():
            self.assertIn("macos-applespell", names)
            self.assertEqual(len(paths), 2)


class TestLinuxPaths(unittest.TestCase):
    def test_app_support_uses_config(self):
        from unittest.mock import patch

        import spell_sync.paths as paths

        with (
            patch.object(paths, "is_windows", return_value=False),
            patch.object(paths, "is_macos", return_value=False),
            patch.object(paths, "home_dir", return_value=Path("/home/user")),
        ):
            self.assertEqual(paths.app_support_dir(), Path("/home/user/.config"))

    def test_discover_dictionaries_skips_macos_on_linux(self):
        from unittest.mock import patch

        import spell_sync.dictionaries as dict_mod

        with (
            patch.object(dict_mod, "is_windows", return_value=False),
            patch.object(dict_mod, "is_macos", return_value=False),
            patch("spell_sync.config.enable_chrome", return_value=False),
        ):
            names = [s.name for s in dict_mod.discover_dictionaries()]
            self.assertNotIn("macos", names)
            self.assertNotIn("macos-applespell", names)


class TestDictionaryDiscoverPlatforms(unittest.TestCase):
    def test_discover_includes_macos_paths(self):
        import spell_sync.dictionaries as dict_mod

        with (
            patch.object(dict_mod, "is_windows", return_value=False),
            patch.object(dict_mod, "is_macos", return_value=True),
            patch.object(dict_mod, "enable_chrome", return_value=False),
            patch.object(dict_mod, "enable_editors", return_value=False),
            patch.object(
                dict_mod,
                "macos_dictionary_paths",
                return_value=[("macos", Path("/tmp/macos"))],
            ),
        ):
            names = [d.name for d in dict_mod.discover_dictionaries()]
            self.assertIn("macos", names)
            self.assertIn("sublime", names)
        with (
            patch.object(dict_mod, "is_windows", return_value=True),
            patch.object(dict_mod, "is_macos", return_value=False),
            patch.object(dict_mod, "enable_chrome", return_value=False),
            patch.object(dict_mod, "enable_editors", return_value=False),
            patch.object(dict_mod, "app_support_dir", return_value=Path("/appdata")),
        ):
            names = [d.name for d in dict_mod.discover_dictionaries()]
            self.assertIn("win-ru", names)
            self.assertIn("win-en", names)
            self.assertIn("win-en-gb", names)


class TestDictionaryDedupe(unittest.TestCase):
    def test_dictionary_read_write_json_and_chrome(self):
        with tempfile.TemporaryDirectory() as d:
            json_path = os.path.join(d, "prefs.json")
            chrome_path = os.path.join(d, "chrome.txt")
            json_dict = Dictionary("sublime", json_path, DictionaryFormat.JSON)
            chrome_dict = Dictionary("chrome", chrome_path, DictionaryFormat.CHROME)
            self.assertTrue(json_dict.write({"alpha"}, quiet=True))
            self.assertTrue(chrome_dict.write({"beta"}, quiet=True))
            self.assertEqual(json_dict.read(quiet=True), {"alpha"})
            self.assertEqual(chrome_dict.read(quiet=True), {"beta"})

    def test_dedupe_warns_duplicate_path(self):
        import spell_sync.dictionaries as dict_mod

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "same.txt")
            write_text_words(path, ["a"], "utf-8", False, quiet=True)
            dictionaries = [
                Dictionary("first", path, DictionaryFormat.TEXT),
                Dictionary("second", path, DictionaryFormat.TEXT),
            ]
            buf = io.StringIO()
            with redirect_stdout(buf):
                deduped = dict_mod._dedupe_dictionaries(dictionaries)
            self.assertEqual(len(deduped), 1)
            self.assertIn("same file", buf.getvalue())

    def test_physical_key_stat_fail_uses_resolve(self):
        import spell_sync.dictionaries as dict_mod

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "file.txt")
            Path(path).write_text("x", encoding="utf-8")
            resolved = Path(d) / "resolved-key.txt"
            with (
                patch("spell_sync.dictionaries.os.stat", side_effect=OSError("stat fail")),
                patch.object(Path, "exists", return_value=True),
                patch.object(Path, "is_symlink", return_value=False),
                patch.object(Path, "resolve", return_value=resolved),
            ):
                key = dict_mod._dictionary_physical_key(path)
            self.assertEqual(key, str(resolved))

    def test_physical_key_oserror_falls_back(self):
        import spell_sync.dictionaries as dict_mod

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "file.txt")
            Path(path).write_text("x", encoding="utf-8")
            with (
                patch("spell_sync.dictionaries.os.stat", side_effect=OSError("stat fail")),
                patch.object(Path, "resolve", side_effect=OSError("bad link")),
            ):
                key = dict_mod._dictionary_physical_key(path)
            self.assertEqual(key, path)

    def test_physical_key_uses_inode_when_available(self):
        import spell_sync.dictionaries as dict_mod

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "file.txt")
            Path(path).write_text("x", encoding="utf-8")
            key = dict_mod._dictionary_physical_key(path)
            self.assertIn(":", key)
            self.assertNotEqual(key, path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
