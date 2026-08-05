"""Unit tests for shell-like path completion."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from spell_sync.tui.path_suggester import complete_path


class TestCompletePath(unittest.TestCase):
    def test_completes_directory_with_trailing_slash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "spell-words").mkdir()
            (root / "other").mkdir()
            suggestion = complete_path(str(root / "sp"))
            self.assertEqual(suggestion, str(root / "spell-words") + "/")

    def test_prefers_wordlist_txt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "wordlist.txt").write_text("a\n", encoding="utf-8")
            (root / "words.txt").write_text("b\n", encoding="utf-8")
            suggestion = complete_path(str(root / "wo"))
            self.assertEqual(suggestion, str(root / "wordlist.txt"))

    def test_preserves_tilde_prefix(self) -> None:
        home = Path.home()
        marker = home / ".spell-sync-path-suggest-test"
        marker.mkdir(exist_ok=True)
        try:
            suggestion = complete_path("~/.spell-sync-path-sug")
            self.assertEqual(suggestion, "~/.spell-sync-path-suggest-test/")
        finally:
            marker.rmdir()

    def test_empty_and_trailing_sep_return_none(self) -> None:
        self.assertIsNone(complete_path(""))
        self.assertIsNone(complete_path("   "))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(complete_path(str(Path(tmp)) + "/"))


if __name__ == "__main__":
    unittest.main()
