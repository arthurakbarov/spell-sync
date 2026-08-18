"""Dictionary rendering for each supported format."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spell_sync.dictionaries import Dictionary, DictionaryFormat
from spell_sync.io import write_text_words
from spell_sync.push_prepared import write_rendered
from spell_sync.push_render import (
    RenderedWrite,
    render_chrome_words,
    render_dictionary,
    render_hunspell_words,
    render_jetbrains_words,
    render_json_words,
    render_text_words,
    render_wordlist,
)
from spell_sync.runtime_settings import RuntimeSettings


class TestPushRenderCoverage(unittest.TestCase):
    def test_text_json_chrome_wordlist(self):
        words = frozenset({"alpha", "beta"})
        self.assertEqual(len(render_wordlist(words).sha256), 64)
        self.assertTrue(render_text_words(words, encoding="utf-8", bom=True).payload)
        self.assertIn(b"added_words", render_json_words(words).payload)
        self.assertIn(b"checksum_v1", render_chrome_words(words).payload)

    def test_hunspell_with_affix_map(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "en.dic")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("2\nalpha/AB\nbeta\n")
            rendered = render_hunspell_words(frozenset({"alpha", "beta"}), path=path)
            self.assertIn(b"alpha/AB", rendered.payload)

    def test_hunspell_reads_when_no_affix_cache(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "en.dic")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("2\nalpha/AB\nbeta\n")
            rendered = render_hunspell_words(frozenset({"alpha", "beta"}), path=path)
            self.assertIn(b"alpha/AB", rendered.payload)
            self.assertIn(b"beta\n", rendered.payload)

    def test_hunspell_render_refreshes_after_external_edit(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "en.dic")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("1\nalpha/AB\n")
            first = render_hunspell_words(frozenset({"alpha"}), path=path)
            self.assertIn(b"alpha/AB", first.payload)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("1\nalpha/XY\n")
            second = render_hunspell_words(frozenset({"alpha"}), path=path)
            self.assertIn(b"alpha/XY", second.payload)
            self.assertNotIn(b"alpha/AB", second.payload)

    def test_jetbrains_existing_xml(self):
        xml = (
            '<?xml version="1.0"?>'
            '<component name="CustomDict"><words><w>old</w></words></component>'
        )
        rendered = render_jetbrains_words(frozenset({"new"}), existing_xml=xml)
        self.assertIn(b"CustomDict", rendered.payload)

    def test_jetbrains_read_from_disk_and_oserror(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "dict.xml"
            path.write_text(
                '<?xml version="1.0"?><component name="X"><words></words></component>',
                encoding="utf-8",
            )
            dictionary = Dictionary("jb", str(path), DictionaryFormat.JETBRAINS)
            self.assertTrue(render_dictionary(dictionary, frozenset({"a"})).payload)
            with patch.object(Path, "read_text", side_effect=OSError("nope")):
                self.assertTrue(render_dictionary(dictionary, frozenset({"a"})).payload)

    def test_render_dictionary_formats(self):
        with tempfile.TemporaryDirectory() as d:
            for fmt, name in (
                (DictionaryFormat.JSON, "prefs.json"),
                (DictionaryFormat.CHROME, "chrome.txt"),
                (DictionaryFormat.HUNSPELL, "en.dic"),
                (DictionaryFormat.TEXT, "words.txt"),
            ):
                path = os.path.join(d, name)
                if fmt is DictionaryFormat.HUNSPELL:
                    write_text_words(path, ["a"], "utf-8", False, quiet=True)
                elif fmt is DictionaryFormat.JSON:
                    Path(path).write_text("{}", encoding="utf-8")
                else:
                    Path(path).write_text("a\n", encoding="utf-8")
                dictionary = Dictionary(fmt.name.lower(), path, fmt)
                self.assertIsInstance(render_dictionary(dictionary, frozenset({"z"})).sha256, str)

    def test_write_rendered_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "out.txt"
            bad = RenderedWrite(b"wrong\n", "0" * 64)
            self.assertFalse(write_rendered(path, bad, settings=RuntimeSettings.defaults()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
