"""Field labels belong next to the control — not as orphan lines in intro prose.

False OK trap that let Change word list ship a blank ``Path to wordlist.txt:``
above the recent list: the label lived both in ``CHANGE_WORDLIST_BODY`` and as a
``Static`` above ``WordlistPathPicker``. Substring checks on the heading alone
never noticed the duplicate.

See ``docs/internal/COPY_STYLE.md`` § Colons and
``docs/internal/TESTING_STRATEGY.md`` § Field-label ownership.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

from spell_sync.application import product_concepts as pc

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]

# Labels that are owned by a dedicated Static / Input chrome next to a control.
# Intro prose constants must not also contain these as bare lines.
_CONTROL_OWNED_FIELD_LABELS = frozenset(
    {
        "Path to wordlist.txt:",
    }
)

_BARE_LABEL_LINE = re.compile(r"^[A-Za-z].{0,80}:\s*$")


def _module_string_constants(module: object) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for name in sorted(dir(module)):
        if name.startswith("_"):
            continue
        value = getattr(module, name)
        if isinstance(value, str) and value.strip():
            out.append((name, value))
    return out


def _bare_control_labels_in_text(text: str) -> list[str]:
    found: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped in _CONTROL_OWNED_FIELD_LABELS:
            found.append(stripped)
    return found


def _string_literals(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append(node.value)
    return out


class TestFieldLabelOwnership(unittest.TestCase):
    def test_product_concepts_prose_does_not_embed_control_labels(self) -> None:
        violations: list[str] = []
        for name, value in _module_string_constants(pc):
            for label in _bare_control_labels_in_text(value):
                violations.append(f"{name} embeds control-owned label {label!r}")
        self.assertEqual(violations, [])

    def test_prose_constants_do_not_end_with_orphan_bare_label(self) -> None:
        """Last line ``Something:`` with no value is almost always a misplaced field label."""
        violations: list[str] = []
        # Section chrome that intentionally ends a prose block (list intro in same string).
        allow_trailing = frozenset(
            {
                # Numbered list heads live in the same constant as their body lines.
            }
        )
        for name, value in _module_string_constants(pc):
            lines = [ln.strip() for ln in value.strip().splitlines() if ln.strip()]
            if not lines:
                continue
            last = lines[-1]
            if name in allow_trailing:
                continue
            if _BARE_LABEL_LINE.match(last) and not last.endswith(("…", "...")):
                # Allow "Usual path after setup:" only when more body follows — already
                # stripped to last line, so a bare trailing label is always a smell.
                violations.append(f"{name} ends with bare label line {last!r}")
        self.assertEqual(violations, [])

    def test_path_label_not_duplicated_inside_change_wordlist_compose_body(self) -> None:
        """Screen source: path label Static must be the only Path to wordlist.txt: there."""
        path = _PACKAGE_ROOT / "spell_sync" / "tui" / "screens" / "setup_welcome_screen.py"
        literals = _string_literals(path)
        # Count exact field-label literals (not mentions inside longer prose).
        exact = [s for s in literals if s.strip() == "Path to wordlist.txt:"]
        # Open existing + Change word list each own one Static label.
        self.assertEqual(
            len(exact),
            2,
            "expected one Path to wordlist.txt: Static per open/change screen",
        )
        # CHANGE_WORDLIST_BODY is imported — ensure compose body assembly does not
        # re-append the label in an f-string / concatenation in this file.
        source = path.read_text(encoding="utf-8")
        self.assertNotIn(
            'CHANGE_WORDLIST_BODY + "\\n\\nPath to wordlist',
            source,
        )
        self.assertNotIn(
            "Path to wordlist.txt:\\n\\nPick a recent",
            source,
        )


if __name__ == "__main__":
    unittest.main()
