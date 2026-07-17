#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Typed dictionary read outcomes."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.read_outcome import ReadStatus, dictionary_read_result


class TestReadOutcome(unittest.TestCase):
    def test_missing_dictionary(self):
        with tempfile.TemporaryDirectory() as d:
            dictionary = Dictionary("a", os.path.join(d, "missing.txt"), DictionaryFormat.TEXT)
            self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.MISSING)

    def test_empty_dictionary(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "empty.txt"
            path.write_text("", encoding="utf-8")
            dictionary = Dictionary("a", str(path), DictionaryFormat.TEXT)
            self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.EMPTY)

    def test_corrupt_json(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "prefs.json"
            path.write_text("{not json", encoding="utf-8")
            dictionary = Dictionary("sublime", str(path), DictionaryFormat.JSON)
            self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.CORRUPT)

    def test_corrupt_jetbrains(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cachedDictionary.xml"
            path.write_text("<broken", encoding="utf-8")
            dictionary = Dictionary(
                "jetbrains:IDEA",
                str(path),
                DictionaryFormat.JETBRAINS,
            )
            self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.CORRUPT)

    def test_ok_json(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "prefs.json"
            path.write_text(json.dumps({"added_words": ["alpha"]}), encoding="utf-8")
            dictionary = Dictionary("sublime", str(path), DictionaryFormat.JSON)
            self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.OK)

    def test_json_unreadable(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "prefs.json"
            path.write_text("{}", encoding="utf-8")
            dictionary = Dictionary("sublime", str(path), DictionaryFormat.JSON)
            with patch("spell_sync.read_outcome.is_path_readable", return_value=False):
                self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.UNREADABLE)

    def test_json_unsupported_added_words_type(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "prefs.json"
            path.write_text(json.dumps({"added_words": "nope"}), encoding="utf-8")
            dictionary = Dictionary("sublime", str(path), DictionaryFormat.JSON)
            self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.UNSUPPORTED)

    def test_json_empty_added_words(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "prefs.json"
            path.write_text(json.dumps({"added_words": []}), encoding="utf-8")
            dictionary = Dictionary("sublime", str(path), DictionaryFormat.JSON)
            self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.EMPTY)

    def test_jetbrains_empty_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "cachedDictionary.xml"
            path.write_text("   \n", encoding="utf-8")
            dictionary = Dictionary(
                "jetbrains:IDEA",
                str(path),
                DictionaryFormat.JETBRAINS,
            )
            self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.EMPTY)

    def test_json_invalid_top_level_type(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "prefs.json"
            path.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
            dictionary = Dictionary("sublime", str(path), DictionaryFormat.JSON)
            self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.CORRUPT)

    def test_text_comments_only_empty(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "words.txt"
            path.write_text("# comment only\n", encoding="utf-8")
            dictionary = Dictionary("a", str(path), DictionaryFormat.TEXT)
            self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.EMPTY)

    def test_text_blank_lines_only_empty(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "words.txt"
            path.write_text("\n\n", encoding="utf-8")
            dictionary = Dictionary("a", str(path), DictionaryFormat.TEXT)
            self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.EMPTY)

    def test_ok_text_dictionary(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "words.txt"
            path.write_text("alpha\n", encoding="utf-8")
            dictionary = Dictionary("a", str(path), DictionaryFormat.TEXT)
            self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.OK)

    def test_chrome_crlf_checksum(self):
        import hashlib

        from spell_sync.config import CHROME_CHECKSUM_PREFIX

        body = "alpha\n"
        checksum = hashlib.md5(body.encode("utf-8")).hexdigest()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "chrome.txt"
            on_disk = body.replace("\n", "\r\n") + CHROME_CHECKSUM_PREFIX + checksum
            path.write_bytes(on_disk.encode("utf-8"))
            dictionary = Dictionary("chrome", str(path), DictionaryFormat.CHROME)
            self.assertEqual(dictionary_read_result(dictionary).status, ReadStatus.OK)
            self.assertEqual(dictionary.read(quiet=True), {"alpha"})
