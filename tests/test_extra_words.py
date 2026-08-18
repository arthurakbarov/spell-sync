"""Extra-word inventory and surgical subtract."""

import tempfile
import unittest
from pathlib import Path

from spell_sync.application.extra_words import (
    build_extra_word_inventory,
    subtract_extra_words_from_sources,
)
from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.io import read_text_words, write_text_words
from spell_sync.words import subset_russian
from tests.runtime_helpers import make_sync_run


class TestExtraWordInventory(unittest.TestCase):
    def test_word_in_two_sources_lists_both_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            chrome = Path(tmp) / "chrome.txt"
            firefox = Path(tmp) / "firefox.txt"
            write_text_words(str(wordlist), ["keep"], "utf-8", False, quiet=True)
            write_text_words(
                str(chrome), ["keep", "shared", "only-chrome"], "utf-8", False, quiet=True
            )
            write_text_words(
                str(firefox), ["keep", "shared", "only-firefox"], "utf-8", False, quiet=True
            )
            run = make_sync_run(
                wordlist,
                dictionaries=[
                    Dictionary("chrome", str(chrome), DictionaryFormat.TEXT),
                    Dictionary("firefox", str(firefox), DictionaryFormat.TEXT),
                ],
            )
            inventory = build_extra_word_inventory(run)
            by_word = {row.word: row.sources for row in inventory.rows}
            self.assertEqual(set(by_word), {"shared", "only-chrome", "only-firefox"})
            self.assertEqual(by_word["shared"], ("chrome", "firefox"))
            self.assertEqual(by_word["only-chrome"], ("chrome",))
            self.assertEqual(by_word["only-firefox"], ("firefox",))
            self.assertNotIn("keep", by_word)

    def test_wordlist_words_are_omitted_casefold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            chrome = Path(tmp) / "chrome.txt"
            write_text_words(str(wordlist), ["Acme"], "utf-8", False, quiet=True)
            write_text_words(str(chrome), ["acme", "NewTerm"], "utf-8", False, quiet=True)
            run = make_sync_run(
                wordlist,
                dictionaries=[Dictionary("chrome", str(chrome), DictionaryFormat.TEXT)],
            )
            inventory = build_extra_word_inventory(run)
            self.assertEqual([row.word for row in inventory.rows], ["NewTerm"])


class TestSubtractExtraWords(unittest.TestCase):
    def test_subtracts_from_every_source_and_keeps_other_extras(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            chrome = Path(tmp) / "chrome.txt"
            firefox = Path(tmp) / "firefox.txt"
            write_text_words(str(wordlist), ["keep"], "utf-8", False, quiet=True)
            write_text_words(
                str(chrome), ["keep", "reject", "stay-chrome"], "utf-8", False, quiet=True
            )
            write_text_words(
                str(firefox), ["keep", "reject", "stay-firefox"], "utf-8", False, quiet=True
            )
            run = make_sync_run(
                wordlist,
                dictionaries=[
                    Dictionary("chrome", str(chrome), DictionaryFormat.TEXT),
                    Dictionary("firefox", str(firefox), DictionaryFormat.TEXT),
                ],
            )
            inventory = build_extra_word_inventory(run)
            result = subtract_extra_words_from_sources(run, inventory, ("reject",))
            self.assertTrue(result.ok)
            self.assertEqual(set(result.written), {"chrome", "firefox"})
            self.assertEqual(read_text_words(str(chrome), quiet=True), {"keep", "stay-chrome"})
            self.assertEqual(read_text_words(str(firefox), quiet=True), {"keep", "stay-firefox"})

    def test_empty_selection_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            chrome = Path(tmp) / "chrome.txt"
            write_text_words(str(wordlist), ["keep"], "utf-8", False, quiet=True)
            write_text_words(str(chrome), ["keep", "extra"], "utf-8", False, quiet=True)
            run = make_sync_run(
                wordlist,
                dictionaries=[Dictionary("chrome", str(chrome), DictionaryFormat.TEXT)],
            )
            inventory = build_extra_word_inventory(run)
            result = subtract_extra_words_from_sources(run, inventory, ())
            self.assertTrue(result.ok)
            self.assertEqual(result.written, ())
            self.assertEqual(read_text_words(str(chrome), quiet=True), {"keep", "extra"})

    def test_write_contents_does_not_apply_subset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            path = Path(tmp) / "win-ru.txt"
            write_text_words(str(wordlist), ["world"], "utf-8", False, quiet=True)
            write_text_words(str(path), ["world", "hello", "привет"], "utf-8", False, quiet=True)
            dictionary = Dictionary(
                "win-ru",
                str(path),
                DictionaryFormat.TEXT,
                subset=subset_russian,
            )
            run = make_sync_run(wordlist, dictionaries=[dictionary])
            inventory = build_extra_word_inventory(run)
            result = subtract_extra_words_from_sources(run, inventory, ("hello",))
            self.assertTrue(result.ok)
            # write() would drop latin "world" via subset_russian; write_contents keeps it.
            self.assertEqual(read_text_words(str(path), quiet=True), {"world", "привет"})

    def test_fingerprint_change_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wordlist = Path(tmp) / "wordlist.txt"
            chrome = Path(tmp) / "chrome.txt"
            write_text_words(str(wordlist), ["keep"], "utf-8", False, quiet=True)
            write_text_words(str(chrome), ["keep", "extra"], "utf-8", False, quiet=True)
            run = make_sync_run(
                wordlist,
                dictionaries=[Dictionary("chrome", str(chrome), DictionaryFormat.TEXT)],
            )
            inventory = build_extra_word_inventory(run)
            write_text_words(str(chrome), ["keep", "extra", "newer"], "utf-8", False, quiet=True)
            result = subtract_extra_words_from_sources(run, inventory, ("extra",))
            self.assertFalse(result.ok)
            self.assertTrue(result.conflict)
            self.assertEqual(read_text_words(str(chrome), quiet=True), {"keep", "extra", "newer"})


if __name__ == "__main__":
    unittest.main()
