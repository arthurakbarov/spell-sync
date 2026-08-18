"""Layout-independent interpretation of keyboard shortcuts and y/n prompts.

Both the TUI's single-letter `Binding`s and the CLI's `input("... [y/N]")`
prompts compare the literal character(s) the terminal reports against a
fixed, QWERTY-assumed string (`"r"`, `"y"`, `"yes"`, ...). That character
depends on whichever OS keyboard layout is active, not on the physical
key: pressing the key at the "R" position produces `"r"` under a
US/QWERTY layout but `"к"` under the Russian "ЙЦУКЕН" layout. A shortcut
or prompt answer written for QWERTY only ever matches the former, so it
silently stops working the moment the terminal's input layout is switched
away from QWERTY.

`qwerty_equivalent` maps a letter produced by a known non-QWERTY layout
back to the QWERTY letter that lives at the same physical key position.
`is_confirmed` uses it to accept y/n prompt answers typed under another
layout. Only single, unmodified letters are ever translated: named keys
(`escape`, `tab`, ...) and control/meta combinations already arrive as
layout-independent identifiers and must not be touched.

Extending to another layout: add a `{typed_letter: qwerty_letter}` table
mapping each letter to the QWERTY key at the same physical position, then
fold it into `_NON_QWERTY_TO_QWERTY` below.
"""

from __future__ import annotations

# Standard Russian "ЙЦУКЕН" layout, keyed by the QWERTY letter that shares
# its physical position (same three rows, left to right).
_RUSSIAN_TO_QWERTY = {
    "й": "q", "ц": "w", "у": "e", "к": "r", "е": "t", "н": "y",
    "г": "u", "ш": "i", "щ": "o", "з": "p",
    "ф": "a", "ы": "s", "в": "d", "а": "f", "п": "g", "р": "h",
    "о": "j", "л": "k", "д": "l",
    "я": "z", "ч": "x", "с": "c", "м": "v", "и": "b", "т": "n",
    "ь": "m",
}  # fmt: skip


def _with_uppercase(mapping: dict[str, str]) -> dict[str, str]:
    combined = dict(mapping)
    combined.update({letter.upper(): qwerty.upper() for letter, qwerty in mapping.items()})
    return combined


_NON_QWERTY_TO_QWERTY: dict[str, str] = _with_uppercase(_RUSSIAN_TO_QWERTY)


def qwerty_equivalent(key: str) -> str | None:
    """Return the QWERTY letter at the same physical position as `key`.

    `key` is a Textual key identifier (`events.Key.key`). Returns `None`
    when `key` is not a single letter from a known non-QWERTY layout, so
    callers can tell "no translation available" apart from "translates to
    itself".
    """
    return _NON_QWERTY_TO_QWERTY.get(key)


CONFIRM_YES = frozenset({"y", "yes"})


def is_confirmed(answer: str) -> bool:
    """True if a y/n prompt `answer` means "yes", typed under any known layout.

    Accepts the literal `"y"`/`"yes"` as well as what the physical keys
    co-located with y-e-s produce under a known non-QWERTY layout.
    """
    normalized = answer.strip().lower()
    if normalized in CONFIRM_YES:
        return True
    translated = "".join(qwerty_equivalent(letter) or letter for letter in normalized)
    return translated in CONFIRM_YES
