#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Symlink, dedup, and pull/push consistency."""

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import spell_sync.dictionaries as dict_mod
import spell_sync.io as io_mod
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.exit_codes import ExitCode
from spell_sync.io import read_text_words, write_text_words
from spell_sync.sync_run import SyncRun


def _can_create_symlinks() -> bool:
    if sys.platform == "win32":
        # Developer Mode or admin required on Windows; CI may lack both.
        return getattr(os, "supports_symlinks", False)
    return hasattr(os, "symlink")


def _symlink_skip_reason() -> str:
    if sys.platform == "win32":
        return "symlinks not supported in this Windows environment"
    return "symlinks not supported"


@unittest.skipUnless(_can_create_symlinks(), _symlink_skip_reason())
class TestAtomicWriteSymlink(unittest.TestCase):
    def test_preserves_symlink_and_updates_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real.txt"
            link = root / "link.txt"
            real.write_text("old\n", encoding="utf-8")
            link.symlink_to(real)

            io_mod.atomic_write(link, b"new\n")

            self.assertTrue(link.is_symlink())
            self.assertEqual(real.read_text(), "new\n")
            self.assertEqual(link.read_text(), "new\n")

    def test_write_text_words_through_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "dict.txt"
            link = root / "link.txt"
            real.write_text("alpha\n", encoding="utf-8")
            link.symlink_to(real)

            write_text_words(str(link), ["beta"], "utf-8", False, quiet=True)

            self.assertTrue(link.is_symlink())
            self.assertEqual(read_text_words(str(link), quiet=True), {"beta"})


@unittest.skipUnless(_can_create_symlinks(), _symlink_skip_reason())
class TestDictionaryDedup(unittest.TestCase):
    def test_skips_second_dictionary_for_same_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = os.path.join(tmp, "real.txt")
            link = os.path.join(tmp, "link.txt")
            write_text_words(real, ["alpha"], "utf-8", False, quiet=True)
            os.symlink(real, link)
            dictionaries = [
                Dictionary("first", real, DictionaryFormat.TEXT),
                Dictionary("second", link, DictionaryFormat.TEXT),
            ]
            deduped = dict_mod._dedupe_dictionaries(dictionaries)
            self.assertEqual(len(deduped), 1)
            self.assertEqual(deduped[0].name, "first")

    def test_push_deduped_dictionaries_writes_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = os.path.join(tmp, "wordlist.txt")
            real = os.path.join(tmp, "real.txt")
            link = os.path.join(tmp, "link.txt")
            write_text_words(wordlist, ["alpha", "beta"], "utf-8", False, quiet=True)
            write_text_words(real, ["stale"], "utf-8", False, quiet=True)
            os.symlink(real, link)
            dictionaries = dict_mod._dedupe_dictionaries(
                [
                    Dictionary("first", real, DictionaryFormat.TEXT),
                    Dictionary("second", link, DictionaryFormat.TEXT),
                ]
            )
            run = SyncRun(wordlist=wordlist, dictionaries=dictionaries)
            result = run.push_from_wordlist()
            self.assertEqual(result.written, ("first",))
            self.assertTrue(os.path.islink(link))
            self.assertEqual(
                read_text_words(real, quiet=True),
                {"alpha", "beta"},
            )


class TestPullReadableGuard(unittest.TestCase):
    def test_pull_skips_unreadable_dictionary_with_warn(self):
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = os.path.join(tmp, "wordlist.txt")
            dict_path = os.path.join(tmp, "dict.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(dict_path, ["beta"], "utf-8", False, quiet=True)
            blocked_dict = Dictionary("blocked", dict_path, DictionaryFormat.TEXT)
            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[blocked_dict],
            )
            with patch("spell_sync.read_outcome.is_path_readable", return_value=False):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    result = run.pull_into_wordlist()
            self.assertEqual(result, (1, 1))
            self.assertEqual(run.load_wordlist(), {"alpha"})
            self.assertIn("pull skipped", buf.getvalue())


class TestMacosPathsNotDeduped(unittest.TestCase):
    def test_classic_and_group_are_separate_when_different_files(self):
        import sys

        if sys.platform != "darwin":
            self.skipTest("macOS only")
        from spell_sync.paths import macos_dictionary_paths

        paths = macos_dictionary_paths()
        if len(paths) < 2:
            self.skipTest("only one macOS dictionary path")
        dictionaries = [Dictionary(name, str(path), DictionaryFormat.TEXT) for name, path in paths]
        deduped = dict_mod._dedupe_dictionaries(dictionaries)
        self.assertEqual(len(deduped), len(dictionaries))


class TestHardlinkDedup(unittest.TestCase):
    def test_hardlinks_deduped_to_one_dictionary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real.txt"
            real.write_text("alpha\n", encoding="utf-8")
            hard = root / "hard.txt"
            os.link(real, hard)
            dictionaries = [
                Dictionary("first", str(real), DictionaryFormat.TEXT),
                Dictionary("second", str(hard), DictionaryFormat.TEXT),
            ]
            deduped = dict_mod._dedupe_dictionaries(dictionaries)
            self.assertEqual(len(deduped), 1)


@unittest.skipUnless(_can_create_symlinks(), _symlink_skip_reason())
class TestBrokenSymlinkWrite(unittest.TestCase):
    def test_broken_symlink_kept_and_target_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            link = root / "link.txt"
            target = root / "missing-target.txt"
            link.symlink_to(target.name)
            io_mod.atomic_write(link, b"hello\n")
            self.assertTrue(link.is_symlink())
            self.assertTrue(target.is_file())
            self.assertEqual(link.read_text(), "hello\n")


@unittest.skipUnless(_can_create_symlinks(), _symlink_skip_reason())
class TestWordlistSymlinkRollback(unittest.TestCase):
    def test_push_failure_restores_symlink_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real-wordlist.txt"
            link = root / "wordlist.txt"
            dict_path = root / "dict.txt"
            real.write_text("alpha\n", encoding="utf-8")
            link.symlink_to(real)
            write_text_words(str(dict_path), ["stale"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=str(link),
                dictionaries=[
                    Dictionary("s", str(dict_path), DictionaryFormat.TEXT),
                ],
            )
            with patch("spell_sync.push_prepared.write_rendered", return_value=False):
                result = run.push_from_wordlist()
            self.assertEqual(result, ExitCode.PUSH_ABORT)
            self.assertTrue(link.is_symlink())
            self.assertEqual(real.read_text(), "alpha\n")
            self.assertEqual(read_text_words(str(dict_path), quiet=True), {"stale"})


@unittest.skipUnless(_can_create_symlinks(), _symlink_skip_reason())
class TestExportThroughSymlink(unittest.TestCase):
    def test_push_aborts_on_empty_broken_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            link = root / "wordlist.txt"
            link.symlink_to("missing-target.txt")
            self.assertFalse(io_mod.wordlist_unreadable(link))
            run = SyncRun(wordlist=str(link), dictionaries=[])
            result = run.push_from_wordlist()
            self.assertEqual(result, ExitCode.PUSH_ABORT)

    def test_pull_creates_target_through_broken_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            link = root / "wordlist.txt"
            target = root / "missing-target.txt"
            link.symlink_to(target.name)
            dict_path = root / "dict.txt"
            write_text_words(str(dict_path), ["beta"], "utf-8", False, quiet=True)
            run = SyncRun(
                wordlist=str(link),
                dictionaries=[
                    Dictionary("s", str(dict_path), DictionaryFormat.TEXT),
                ],
            )
            result = run.pull_into_wordlist()
            self.assertEqual(result, (0, 1))
            self.assertTrue(link.is_symlink())
            self.assertTrue(target.is_file())
            self.assertEqual(read_text_words(str(link), quiet=True), {"beta"})


@unittest.skipUnless(_can_create_symlinks(), _symlink_skip_reason())
class TestStrictPushSymlinkBackup(unittest.TestCase):
    def test_strict_aborts_when_symlink_dict_backup_fails(self):
        import spell_sync.push_transaction as push_tx

        with tempfile.TemporaryDirectory() as tmp:
            wordlist = os.path.join(tmp, "wordlist.txt")
            path_ok = os.path.join(tmp, "ok.txt")
            real = os.path.join(tmp, "real.txt")
            link = os.path.join(tmp, "link.txt")
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            write_text_words(path_ok, ["stale"], "utf-8", False, quiet=True)
            write_text_words(real, ["stale"], "utf-8", False, quiet=True)
            os.symlink(real, link)

            original_copy = push_tx.shutil.copy2

            def selective_copy(src, dst, **kwargs):
                if Path(src).resolve() == Path(real).resolve():
                    raise OSError("backup denied")
                return original_copy(src, dst, **kwargs)

            run = SyncRun(
                wordlist=wordlist,
                dictionaries=[
                    Dictionary("ok", path_ok, DictionaryFormat.TEXT),
                    Dictionary("linked", link, DictionaryFormat.TEXT),
                ],
                strict_push=True,
            )
            with patch.object(push_tx.shutil, "copy2", side_effect=selective_copy):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    result = run.push_from_wordlist()
            self.assertEqual(result, ExitCode.PUSH_ABORT)
            self.assertIn("--strict", buf.getvalue())
            self.assertIn("backup failed", buf.getvalue())
            self.assertEqual(read_text_words(path_ok, quiet=True), {"stale"})
            self.assertEqual(read_text_words(real, quiet=True), {"stale"})


class TestBundledExamples(unittest.TestCase):
    def test_bundled_examples_exist(self):
        from spell_sync.bundled_files import bundled_path

        for name in (
            "wordlist.txt.example",
            "spell-sync.toml.example",
            "lint-whitelist.txt",
        ):
            path = bundled_path(name)
            self.assertTrue(path.is_file(), f"missing bundled/{name}")
            self.assertTrue(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
