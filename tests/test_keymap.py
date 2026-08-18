"""Tests for layout-independent key binding translation and y/n prompts."""

import unittest

from spell_sync.keymap import is_confirmed, qwerty_equivalent


class TestQwertyEquivalent(unittest.TestCase):
    def test_translates_russian_letters_used_by_tui_bindings(self):
        # Physical positions of every single-letter TUI binding (q, r, s, h, v, a, b).
        cases = {
            "й": "q",
            "к": "r",
            "ы": "s",
            "р": "h",
            "м": "v",
            "ф": "a",
            "и": "b",
        }
        for russian, qwerty in cases.items():
            with self.subTest(russian=russian):
                self.assertEqual(qwerty_equivalent(russian), qwerty)

    def test_preserves_case(self):
        self.assertEqual(qwerty_equivalent("К"), "R")

    def test_unknown_letter_returns_none(self):
        self.assertIsNone(qwerty_equivalent("r"))
        self.assertIsNone(qwerty_equivalent("z"))

    def test_named_keys_are_not_translated(self):
        self.assertIsNone(qwerty_equivalent("escape"))
        self.assertIsNone(qwerty_equivalent("ctrl+q"))


class TestIsConfirmed(unittest.TestCase):
    def test_accepts_plain_yes(self):
        for answer in ("y", "Y", "yes", " Yes \n"):
            with self.subTest(answer=answer):
                self.assertTrue(is_confirmed(answer))

    def test_rejects_plain_no(self):
        for answer in ("n", "no", "", "maybe"):
            with self.subTest(answer=answer):
                self.assertFalse(is_confirmed(answer))

    def test_accepts_russian_layout_yes(self):
        # "н" and "нуы" sit at the physical y and y-e-s keys on ЙЦУКЕН.
        self.assertTrue(is_confirmed("н"))
        self.assertTrue(is_confirmed("нуы"))

    def test_rejects_unrelated_cyrillic_text(self):
        self.assertFalse(is_confirmed("да"))


if __name__ == "__main__":
    unittest.main()
