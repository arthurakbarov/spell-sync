#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dictionary discovery for browser targets."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spell_sync.dictionaries import discover_dictionaries


class TestBraveVivaldiDiscovery(unittest.TestCase):
    def test_discover_includes_brave_and_vivaldi(self):
        with tempfile.TemporaryDirectory() as d:
            brave_base = Path(d) / "brave"
            vivaldi_base = Path(d) / "vivaldi"
            (brave_base / "Default").mkdir(parents=True)
            (vivaldi_base / "Default").mkdir(parents=True)
            brave_custom = brave_base / "Default" / "Custom Dictionary.txt"
            vivaldi_custom = vivaldi_base / "Default" / "Custom Dictionary.txt"
            with (
                patch("spell_sync.dictionaries.enable_chrome", return_value=False),
                patch("spell_sync.dictionaries.enable_edge", return_value=False),
                patch("spell_sync.dictionaries.enable_editors", return_value=False),
                patch("spell_sync.dictionaries.enable_firefox", return_value=False),
                patch("spell_sync.dictionaries.enable_neovim", return_value=False),
                patch("spell_sync.dictionaries.enable_jetbrains", return_value=False),
                patch("spell_sync.dictionaries.enable_hunspell", return_value=False),
                patch("spell_sync.dictionaries.enable_obsidian", return_value=False),
                patch("spell_sync.dictionaries.enable_libreoffice", return_value=False),
                patch("spell_sync.dictionaries.is_windows", return_value=False),
                patch("spell_sync.dictionaries.is_macos", return_value=False),
                patch(
                    "spell_sync.dictionaries.brave_dict_paths",
                    return_value=[("Default", brave_custom)],
                ),
                patch(
                    "spell_sync.dictionaries.vivaldi_dict_paths",
                    return_value=[("Default", vivaldi_custom)],
                ),
            ):
                names = [d.name for d in discover_dictionaries()]
            self.assertIn("brave:Default", names)
            self.assertIn("vivaldi:Default", names)

    def test_discover_includes_chrome_profiles(self):
        with tempfile.TemporaryDirectory() as d:
            chrome_custom = Path(d) / "Default" / "Custom Dictionary.txt"
            chrome_custom.parent.mkdir(parents=True)
            chrome_custom.write_text("word\n", encoding="utf-8")
            with (
                patch("spell_sync.dictionaries.enable_chrome", return_value=True),
                patch("spell_sync.dictionaries.enable_edge", return_value=False),
                patch("spell_sync.dictionaries.enable_editors", return_value=False),
                patch("spell_sync.dictionaries.enable_firefox", return_value=False),
                patch("spell_sync.dictionaries.enable_neovim", return_value=False),
                patch("spell_sync.dictionaries.enable_jetbrains", return_value=False),
                patch("spell_sync.dictionaries.enable_hunspell", return_value=False),
                patch("spell_sync.dictionaries.enable_obsidian", return_value=False),
                patch("spell_sync.dictionaries.enable_libreoffice", return_value=False),
                patch("spell_sync.dictionaries.is_windows", return_value=False),
                patch("spell_sync.dictionaries.is_macos", return_value=False),
                patch(
                    "spell_sync.dictionaries.chrome_dict_paths",
                    return_value=[("Default", chrome_custom)],
                ),
            ):
                names = [item.name for item in discover_dictionaries()]
            self.assertIn("chrome:Default", names)


if __name__ == "__main__":
    import unittest

    unittest.main(verbosity=2)
