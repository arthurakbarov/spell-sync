"""Unit tests for shell-like path completion listing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from spell_sync.tui.path_suggester import complete_path, list_path_completions


class TestListPathCompletions(unittest.TestCase):
    def test_trailing_slash_lists_directory_without_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "alpha").mkdir()
            (root / "beta").mkdir()
            (root / "wordlist.txt").write_text("a\n", encoding="utf-8")
            (root / "notes.txt").write_text("b\n", encoding="utf-8")
            hits = list_path_completions(str(root) + "/")
            prompts = [hit.prompt for hit in hits]
            self.assertEqual(prompts[:2], ["alpha/", "beta/"])
            self.assertIn("wordlist.txt", prompts)
            self.assertIn("notes.txt", prompts)
            self.assertTrue(all(hit.value.startswith(str(root)) for hit in hits))

    def test_prefix_filters_multiple_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "spell-words").mkdir()
            (root / "spell-sync").mkdir()
            (root / "other").mkdir()
            hits = list_path_completions(str(root / "sp"))
            prompts = [hit.prompt for hit in hits]
            self.assertEqual(prompts, ["spell-sync/", "spell-words/"])

    def test_prefers_wordlist_among_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "wordlist.txt").write_text("a\n", encoding="utf-8")
            (root / "words.txt").write_text("b\n", encoding="utf-8")
            hits = list_path_completions(str(root / "wo"))
            self.assertEqual(hits[0].prompt, "wordlist.txt")

    def test_empty_lists_home_style_entries(self) -> None:
        home = Path.home()
        (home / "Documents").mkdir(exist_ok=True)
        (home / "code").mkdir(exist_ok=True)
        hits = list_path_completions("")
        self.assertGreater(len(hits), 0)
        self.assertTrue(all(hit.value.startswith("~/") for hit in hits))
        prompts = {hit.prompt for hit in hits}
        self.assertIn("Documents/", prompts)
        self.assertIn("code/", prompts)

    def test_complete_path_returns_first_hit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "spell-words").mkdir()
            (root / "other").mkdir()
            self.assertEqual(complete_path(str(root / "sp")), str(root / "spell-words") + "/")

    def test_missing_directory_returns_empty(self) -> None:
        self.assertEqual(list_path_completions("/no/such/path/here/"), [])


if __name__ == "__main__":
    unittest.main()
