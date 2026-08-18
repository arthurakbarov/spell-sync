"""Application custom dictionary model and on-disk formats.

Kept free of discovery and parsing so the typed reader (:mod:`read_outcome`) can
depend on the model without importing the heavier discovery stack. Reading a
dictionary defers to :mod:`read_outcome` at call time.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from .io import (
    write_chrome_words,
    write_hunspell_words,
    write_jetbrains_words,
    write_json_words,
    write_text_words,
)
from .words import WordSet

type SubsetFn = Callable[[WordSet], WordSet]


class DictionaryFormat(StrEnum):
    CHROME = "chrome"
    HUNSPELL = "hunspell"
    JSON = "json"
    JETBRAINS = "jetbrains"
    TEXT = "text"


@dataclass(frozen=True)
class Dictionary:
    """One application custom dictionary file discovered for sync.

    Spell Sync reads and writes user custom dictionary storage (for example browser
    custom word lists or IDE user dictionaries). Built-in application dictionaries
    shipped with applications are never read, modified, or inspected.
    """

    name: str
    path: str
    format: DictionaryFormat
    encoding: str = "utf-8"
    bom: bool = False
    subset: SubsetFn | None = None

    def target_words(self, wordlist: WordSet) -> WordSet:
        """Return the personal word-list subset written to this target.

        When ``subset`` is set (for example Windows locale custom dictionaries),
        only matching script words are pushed: ``filter_i(W)`` instead of full ``W``.
        """
        return self.subset(wordlist) if self.subset else wordlist

    def read(self, *, quiet: bool | None = None) -> WordSet:
        """Read words via the typed full-file classifier (fail-closed parsers only)."""
        from .read_outcome import dictionary_read_result, is_readable_for_union

        result = dictionary_read_result(self)
        if not is_readable_for_union(result.status):
            return set()
        return set(result.words)

    def write(self, wordlist: WordSet, *, quiet: bool | None = None) -> bool:
        return self.write_contents(self.target_words(wordlist), quiet=quiet)

    def write_contents(self, words: WordSet, *, quiet: bool | None = None) -> bool:
        """Write ``words`` as this file's contents (no subset filter).

        ``write`` applies ``target_words`` first (``filter_i(W)``). Surgical
        subtracts must use this method so leftover extra words stay on disk.
        """
        writers = {
            DictionaryFormat.JSON: lambda: write_json_words(self.path, words, quiet=quiet),
            DictionaryFormat.CHROME: lambda: write_chrome_words(self.path, words, quiet=quiet),
            DictionaryFormat.HUNSPELL: lambda: write_hunspell_words(self.path, words, quiet=quiet),
            DictionaryFormat.JETBRAINS: lambda: write_jetbrains_words(
                self.path, words, quiet=quiet
            ),
        }
        write_fn = writers.get(self.format)
        if write_fn is not None:
            return write_fn()
        return write_text_words(self.path, words, self.encoding, self.bom, quiet=quiet)
