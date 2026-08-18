"""Pull preview honesty: casefold normalize, NFC, corrupt add-from."""

import subprocess
import tempfile
import unicodedata
import unittest
from pathlib import Path

from spell_sync.application.push_pull_preview_builders import (
    build_pull_add_from_preview,
    build_pull_preview,
)
from spell_sync.exit_codes import ExitCode
from spell_sync.io import write_text_words
from spell_sync.words import added_words_casefold, union_words_casefold
from tests.runtime_helpers import make_sync_run


class TestPullPreviewHonesty(unittest.TestCase):
    def test_casefold_duplicates_do_not_report_negative_additions(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            write_text_words(str(wordlist), ["Foo", "foo"], "utf-8", False, quiet=True)
            preview = build_pull_preview(make_sync_run(str(wordlist), dictionaries=[]))
            self.assertEqual(preview.before_count, 1)
            self.assertEqual(preview.after_count, 1)
            self.assertEqual(preview.additions, 0)
            self.assertGreaterEqual(preview.additions, 0)

    def test_nfc_and_nfd_spellings_union_once(self):
        nfc = "café"
        nfd = unicodedata.normalize("NFD", nfc)
        self.assertEqual(union_words_casefold([nfc], [nfd]), [nfc])

    def test_corrupt_add_from_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            write_text_words(str(wordlist), ["alpha"], "utf-8", False, quiet=True)
            corrupt = Path(d) / "extra.dic"
            corrupt.write_bytes(b"\xff\xfe\x00")
            preview = build_pull_add_from_preview(
                make_sync_run(str(wordlist), dictionaries=[]),
                corrupt,
            )
            self.assertEqual(preview.prepare_error, ExitCode.WORDLIST_UNREADABLE)
            self.assertEqual(preview.additions, 0)
            self.assertTrue(any("Skipped unreadable" in warning for warning in preview.warnings))
            self.assertFalse(any("Skipped corrupt" in warning for warning in preview.warnings))

    def test_add_from_dic_with_control_characters_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            wordlist = Path(d) / "wordlist.txt"
            write_text_words(str(wordlist), ["alpha"], "utf-8", False, quiet=True)
            corrupt = Path(d) / "extra.dic"
            corrupt.write_text("beta\x00gamma\n", encoding="utf-8")
            preview = build_pull_add_from_preview(
                make_sync_run(str(wordlist), dictionaries=[]),
                corrupt,
            )
            self.assertEqual(preview.prepare_error, ExitCode.WORDLIST_UNREADABLE)
            self.assertEqual(preview.additions, 0)
            self.assertFalse(preview.is_executable)

    def test_add_from_includes_dirty_workspace_warning(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            wordlist = root / "wordlist.txt"
            wordlist.write_text("alpha\n", encoding="utf-8")
            (root / "spell-sync.toml").write_text("[dictionaries]\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "wordlist.txt", "spell-sync.toml"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "initial"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            wordlist.write_text("alpha\nbeta\n", encoding="utf-8")
            extra = root / "extra.txt"
            extra.write_text("gamma\n", encoding="utf-8")
            run = make_sync_run(str(wordlist), dictionaries=[])
            preview = build_pull_add_from_preview(run, extra)
            self.assertEqual(preview.additions, 1)
            self.assertTrue(any("git-save" in warning for warning in preview.warnings))

    def test_added_words_casefold_skips_existing_spelling(self):
        self.assertEqual(added_words_casefold(["Foo"], ["foo", "bar"]), ["bar"])


if __name__ == "__main__":
    unittest.main()
