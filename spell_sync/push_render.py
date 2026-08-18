"""Pure dictionary rendering for push (payload + hash before write)."""

import hashlib
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from .config import CHROME_CHECKSUM_PREFIX
from .dictionaries import Dictionary, DictionaryFormat
from .io import (
    _jetbrains_words_from_xml,
    _text_payload_bytes,
    format_hunspell_payload,
    load_hunspell_affixes,
)
from .words import WordSet, sort_words


@dataclass(frozen=True)
class RenderedWrite:
    payload: bytes
    sha256: str


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def render_text_words(words: WordSet, *, encoding: str, bom: bool) -> RenderedWrite:
    payload_text = "\n".join(sort_words(words)) + "\n"
    data = _text_payload_bytes(payload_text, encoding, bom)
    return RenderedWrite(data, _sha256_bytes(data))


def render_json_words(words: WordSet) -> RenderedWrite:
    data = json.dumps({"added_words": sort_words(words)}, ensure_ascii=False, indent=2).encode(
        "utf-8"
    )
    return RenderedWrite(data, _sha256_bytes(data))


def render_chrome_words(words: WordSet) -> RenderedWrite:
    sorted_words = sort_words(words)
    body = "".join(word + "\n" for word in sorted_words)
    checksum = hashlib.md5(body.encode("utf-8")).hexdigest()
    data = (body + CHROME_CHECKSUM_PREFIX + checksum).encode("utf-8")
    return RenderedWrite(data, _sha256_bytes(data))


def render_hunspell_words(words: WordSet, *, path: str) -> RenderedWrite:
    # Always load affixes from the live file — no process-global cache.
    affix_map = load_hunspell_affixes(path)
    data = format_hunspell_payload(words, affix_map)
    return RenderedWrite(data, _sha256_bytes(data))


def render_jetbrains_words(words: WordSet, *, existing_xml: str | None) -> RenderedWrite:
    component_name = "CachedDictionaryState"
    if existing_xml:
        _, name, parsed = _jetbrains_words_from_xml(existing_xml)
        if parsed and name:
            component_name = name
    root = ET.Element("component", {"name": component_name})
    words_elem = ET.SubElement(root, "words")
    for word in sort_words(words):
        elem = ET.SubElement(words_elem, "w")
        elem.text = word
    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return RenderedWrite(data, _sha256_bytes(data))


def render_wordlist(words: WordSet) -> RenderedWrite:
    return render_text_words(words, encoding="utf-8", bom=False)


def render_dictionary(dictionary: Dictionary, words: WordSet) -> RenderedWrite:
    target = dictionary.target_words(words)
    fmt = dictionary.format
    if fmt is DictionaryFormat.JSON:
        return render_json_words(target)
    if fmt is DictionaryFormat.CHROME:
        return render_chrome_words(target)
    if fmt is DictionaryFormat.HUNSPELL:
        return render_hunspell_words(target, path=dictionary.path)
    if fmt is DictionaryFormat.JETBRAINS:
        existing: str | None = None
        path = dictionary.path
        try:
            from pathlib import Path

            p = Path(path)
            if p.is_file():
                existing = p.read_text(encoding="utf-8", errors="strict")
        except OSError, UnicodeError:
            existing = None
        return render_jetbrains_words(target, existing_xml=existing)
    return render_text_words(target, encoding=dictionary.encoding, bom=dictionary.bom)
