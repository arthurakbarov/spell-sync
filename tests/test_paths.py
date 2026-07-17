#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""paths.py discovery and platform helpers."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import spell_sync.paths as paths_mod


class TestPathsHelpers(unittest.TestCase):
    def test_repo_and_wordlist_paths(self):
        self.assertTrue(paths_mod.project_root().is_dir())
        self.assertEqual(paths_mod.wordlist_path().name, "wordlist.txt")

    def test_windows_app_support(self):
        with (
            patch.object(paths_mod, "is_windows", return_value=True),
            patch.dict(os.environ, {"APPDATA": "/appdata"}, clear=False),
        ):
            self.assertEqual(paths_mod.app_support_dir(), Path("/appdata"))

    def test_macos_app_support(self):
        with (
            patch.object(paths_mod, "is_macos", return_value=True),
            patch.object(paths_mod, "is_windows", return_value=False),
        ):
            self.assertIn("Application Support", str(paths_mod.app_support_dir()))

    def test_editor_fallback_when_no_editors(self):
        with patch.object(
            paths_mod,
            "editor_user_dirs",
            return_value=[("cursor", Path("/no/cursor"))],
        ):
            pairs = paths_mod.editor_dict_paths()
            self.assertEqual(len(pairs), 1)
            self.assertEqual(pairs[0][0], "cursor")

    def test_chrome_dict_paths_empty_when_no_user_data(self):
        with patch.object(paths_mod, "chrome_user_data_dir", return_value=Path("/no/chrome")):
            self.assertEqual(paths_mod.chrome_dict_paths(), [])

    def test_chrome_dict_paths_oserror_on_iterdir(self):
        base = Path("/fake/chrome")
        with (
            patch.object(paths_mod, "chrome_user_data_dir", return_value=base),
            patch.object(Path, "is_dir", return_value=True),
            patch.object(Path, "iterdir", side_effect=OSError("denied")),
        ):
            self.assertEqual(paths_mod.chrome_dict_paths(), [])

    def test_chrome_user_data_windows(self):
        with (
            patch.object(paths_mod, "is_windows", return_value=True),
            patch.dict(os.environ, {"LOCALAPPDATA": "/local"}, clear=False),
        ):
            path = paths_mod.chrome_user_data_dir()
            self.assertIn("Google", str(path))

    def test_first_existing_dir_returns_default(self):
        missing = [Path("/nonexistent-a"), Path("/nonexistent-b")]
        self.assertEqual(
            paths_mod.first_existing_dir(missing, Path("/d")),
            Path("/d"),
        )

    def test_first_existing_dir_returns_first_match(self):
        with tempfile.TemporaryDirectory() as d:
            existing = Path(d)
            missing = Path("/nonexistent-a")
            self.assertEqual(
                paths_mod.first_existing_dir([missing, existing], Path("/d")),
                existing,
            )

    def test_is_spell_sync_project_wordlist_marker(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "wordlist.txt").write_text("alpha\n", encoding="utf-8")
            self.assertTrue(paths_mod._is_spell_sync_project(root))

    def test_macos_dictionary_paths_includes_group_container(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            spelling = (
                home
                / "Library"
                / "Group Containers"
                / "group.com.apple.AppleSpell"
                / "Library"
                / "Spelling"
            )
            spelling.mkdir(parents=True)
            with patch.object(paths_mod, "home_dir", return_value=home):
                pairs = paths_mod.macos_dictionary_paths()
            names = [name for name, _ in pairs]
            self.assertIn("macos", names)
            self.assertIn("macos-applespell", names)

    def test_edge_user_data_linux(self):
        with (
            patch.object(paths_mod, "is_windows", return_value=False),
            patch.object(paths_mod, "is_macos", return_value=False),
            patch.object(paths_mod, "home_dir", return_value=Path("/home/u")),
        ):
            self.assertEqual(
                paths_mod.edge_user_data_dir(),
                Path("/home/u/.config/microsoft-edge"),
            )

    def test_brave_user_data_linux(self):
        with (
            patch.object(paths_mod, "is_windows", return_value=False),
            patch.object(paths_mod, "is_macos", return_value=False),
            patch.object(paths_mod, "home_dir", return_value=Path("/home/u")),
        ):
            self.assertEqual(
                paths_mod.brave_user_data_dir(),
                Path("/home/u/.config/BraveSoftware/Brave-Browser"),
            )

    def test_brave_user_data_macos(self):
        with (
            patch.object(paths_mod, "is_windows", return_value=False),
            patch.object(paths_mod, "is_macos", return_value=True),
            patch.object(paths_mod, "app_support_dir", return_value=Path("/lib/App Support")),
        ):
            self.assertIn("BraveSoftware", str(paths_mod.brave_user_data_dir()))

    def test_vivaldi_user_data_macos(self):
        with (
            patch.object(paths_mod, "is_windows", return_value=False),
            patch.object(paths_mod, "is_macos", return_value=True),
            patch.object(paths_mod, "app_support_dir", return_value=Path("/lib/App Support")),
        ):
            self.assertIn("Vivaldi", str(paths_mod.vivaldi_user_data_dir()))

    def test_vivaldi_user_data_windows(self):
        with (
            patch.object(paths_mod, "is_windows", return_value=True),
            patch.object(paths_mod, "is_macos", return_value=False),
            patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\u\AppData\Local"}, clear=False),
        ):
            self.assertIn("Vivaldi", str(paths_mod.vivaldi_user_data_dir()))

    def test_firefox_profiles_linux(self):
        with (
            patch.object(paths_mod, "is_windows", return_value=False),
            patch.object(paths_mod, "is_macos", return_value=False),
            patch.object(paths_mod, "home_dir", return_value=Path("/home/u")),
        ):
            self.assertEqual(
                paths_mod.firefox_profiles_dir(),
                Path("/home/u/.mozilla/firefox"),
            )

    def test_neovim_data_dir_linux_default(self):
        env = os.environ.copy()
        env.pop("XDG_DATA_HOME", None)
        with (
            patch.object(paths_mod, "is_windows", return_value=False),
            patch.object(paths_mod, "home_dir", return_value=Path("/home/u")),
            patch.dict(os.environ, env, clear=True),
        ):
            self.assertEqual(
                paths_mod.neovim_data_dir(),
                Path("/home/u/.local/share/nvim"),
            )

    def test_libreoffice_user_dir_linux(self):
        with (
            patch.object(paths_mod, "is_windows", return_value=False),
            patch.object(paths_mod, "is_macos", return_value=False),
            patch.object(paths_mod, "home_dir", return_value=Path("/home/u")),
        ):
            self.assertEqual(
                paths_mod.libreoffice_user_dir(),
                Path("/home/u/.config/libreoffice/4/user"),
            )

    def test_libreoffice_user_dir_macos(self):
        with (
            patch.object(paths_mod, "is_windows", return_value=False),
            patch.object(paths_mod, "is_macos", return_value=True),
            patch.object(paths_mod, "app_support_dir", return_value=Path("/lib/App Support")),
        ):
            self.assertEqual(
                paths_mod.libreoffice_user_dir(),
                Path("/lib/App Support/LibreOffice/4/user"),
            )

    def test_editor_dict_paths_uses_existing_editor_dir(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            cursor_user = base / "Cursor" / "User"
            cursor_user.mkdir(parents=True)
            with patch.object(paths_mod, "app_support_dir", return_value=base):
                pairs = paths_mod.editor_dict_paths()
            self.assertEqual(pairs[0][0], "cursor")
            self.assertEqual(pairs[0][1].name, "spell-sync-words.txt")

    def test_sublime_packages_dir_windows(self):
        with (
            patch.object(paths_mod, "is_macos", return_value=False),
            patch.object(paths_mod, "is_windows", return_value=True),
            patch.object(paths_mod, "app_support_dir", return_value=Path("/appdata")),
        ):
            candidates = paths_mod._sublime_packages_candidates()
            self.assertTrue(any("Sublime Text" in str(path) for path in candidates))

    def test_chrome_user_data_linux(self):
        with (
            patch.object(paths_mod, "is_windows", return_value=False),
            patch.object(paths_mod, "is_macos", return_value=False),
            patch.object(paths_mod, "home_dir", return_value=Path("/home/u")),
        ):
            self.assertEqual(
                paths_mod.chrome_user_data_dir(),
                Path("/home/u/.config/google-chrome"),
            )

    def test_chrome_user_data_macos(self):
        with (
            patch.object(paths_mod, "is_windows", return_value=False),
            patch.object(paths_mod, "is_macos", return_value=True),
        ):
            self.assertIn("Google", str(paths_mod.chrome_user_data_dir()))
        with (
            patch.object(paths_mod, "is_macos", return_value=False),
            patch.object(paths_mod, "is_windows", return_value=False),
            patch.object(paths_mod, "home_dir", return_value=Path("/home/u")),
        ):
            dirs = paths_mod._sublime_packages_candidates()
            self.assertTrue(any("sublime-text" in str(p) for p in dirs))

    def test_project_root_falls_back_to_package_dir(self):
        fake_repo = Path("/fake/spell-sync")
        with (
            patch("spell_sync.paths.Path.cwd", return_value=Path("/tmp/work")),
            patch.object(paths_mod, "REPO_DIR", fake_repo),
            patch.object(
                paths_mod,
                "_is_spell_sync_project",
                side_effect=lambda directory: directory == fake_repo,
            ),
        ):
            self.assertEqual(paths_mod.project_root(), fake_repo)

    def test_is_spell_sync_project_pyproject_needs_package_dir(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "spell-sync"\n', encoding="utf-8"
            )
            self.assertFalse(paths_mod._is_spell_sync_project(root))
            (root / "spell_sync").mkdir()
            self.assertTrue(paths_mod._is_spell_sync_project(root))

    def test_firefox_profiles_dir_windows(self):
        with (
            patch.object(paths_mod, "is_windows", return_value=True),
            patch.object(paths_mod, "is_macos", return_value=False),
            patch.dict(os.environ, {"APPDATA": "/appdata"}, clear=False),
        ):
            path = paths_mod.firefox_profiles_dir()
            self.assertIn("Mozilla", str(path))
            self.assertIn("Firefox", str(path))

    def test_neovim_data_dir_windows(self):
        with (
            patch.object(paths_mod, "is_windows", return_value=True),
            patch.dict(os.environ, {"LOCALAPPDATA": "/localappdata"}, clear=False),
        ):
            self.assertEqual(
                paths_mod.neovim_data_dir(),
                Path("/localappdata") / "nvim-data",
            )

    def test_neovim_data_dir_xdg(self):
        with (
            patch.object(paths_mod, "is_windows", return_value=False),
            patch.dict(os.environ, {"XDG_DATA_HOME": "/xdg/data"}, clear=False),
        ):
            self.assertEqual(
                paths_mod.neovim_data_dir(),
                Path("/xdg/data") / "nvim",
            )

    def test_firefox_dict_paths_oserror_on_iterdir(self):
        base = Path("/fake/firefox")
        with (
            patch.object(paths_mod, "firefox_profiles_dir", return_value=base),
            patch.object(Path, "is_dir", return_value=True),
            patch.object(Path, "iterdir", side_effect=OSError("denied")),
        ):
            self.assertEqual(paths_mod.firefox_dict_paths(), [])

    def test_jetbrains_config_dir_uses_app_support_on_desktop(self):
        with (
            patch.object(paths_mod, "is_macos", return_value=True),
            patch.object(paths_mod, "is_windows", return_value=False),
            patch.object(
                paths_mod,
                "app_support_dir",
                return_value=Path("/appdata/JetBrains-root"),
            ),
        ):
            self.assertEqual(
                paths_mod.jetbrains_config_dir(),
                Path("/appdata/JetBrains-root") / "JetBrains",
            )

    def test_jetbrains_dict_paths_oserror_on_iterdir(self):
        base = Path("/fake/jetbrains")
        with (
            patch.object(paths_mod, "jetbrains_config_dir", return_value=base),
            patch.object(Path, "is_dir", return_value=True),
            patch.object(Path, "iterdir", side_effect=OSError("denied")),
        ):
            self.assertEqual(paths_mod.jetbrains_dict_paths(), [])

    def test_hunspell_windows_candidates(self):
        with (
            patch.object(paths_mod, "is_macos", return_value=False),
            patch.object(paths_mod, "is_windows", return_value=True),
            patch.object(paths_mod, "app_support_dir", return_value=Path("/appdata")),
            patch.object(paths_mod, "home_dir", return_value=Path("/home/u")),
        ):
            labels = [label for label, _ in paths_mod._hunspell_fixed_candidates()]
            self.assertIn("default", labels)
            self.assertTrue(
                any("appdata" in str(path) for _, path in paths_mod._hunspell_fixed_candidates())
            )

    def test_hunspell_config_dir_scans_dic_files(self):
        with tempfile.TemporaryDirectory() as d:
            config_dir = Path(d) / ".config" / "hunspell"
            config_dir.mkdir(parents=True)
            (config_dir / "en_US.dic").write_text("1\nalpha\n", encoding="utf-8")
            (config_dir / "notes.txt").write_text("alpha\n", encoding="utf-8")
            (config_dir / "skip.conf").write_text("skip", encoding="utf-8")
            (config_dir / "subdir").mkdir()
            with patch.object(paths_mod, "home_dir", return_value=Path(d)):
                pairs = paths_mod.hunspell_dict_paths()
            names = [name for name, _ in pairs]
            self.assertIn("en_US.dic", names)
            self.assertIn("notes.txt", names)
            self.assertNotIn("skip.conf", names)
            self.assertNotIn("subdir", names)

    def test_firefox_profiles_dir_macos(self):
        with (
            patch.object(paths_mod, "is_windows", return_value=False),
            patch.object(paths_mod, "is_macos", return_value=True),
            patch.object(paths_mod, "app_support_dir", return_value=Path("/lib/App Support")),
        ):
            path = paths_mod.firefox_profiles_dir()
            self.assertIn("Firefox", str(path))


class TestBraveVivaldiPaths(unittest.TestCase):
    def test_brave_dict_paths_empty_when_no_user_data(self):
        with patch.object(paths_mod, "brave_user_data_dir", return_value=Path("/no/brave")):
            self.assertEqual(paths_mod.brave_dict_paths(), [])

    def test_brave_dict_paths_finds_profiles(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "Default").mkdir(parents=True)
            (base / "Profile 2").mkdir(parents=True)
            with patch.object(paths_mod, "brave_user_data_dir", return_value=base):
                pairs = paths_mod.brave_dict_paths()
            names = [name for name, _ in pairs]
            self.assertIn("Default", names)
            self.assertIn("Profile 2", names)

    def test_brave_user_data_windows(self):
        with (
            patch.object(paths_mod, "is_windows", return_value=True),
            patch.object(paths_mod, "is_macos", return_value=False),
            patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\u\AppData\Local"}, clear=False),
        ):
            path = paths_mod.brave_user_data_dir()
            self.assertIn("BraveSoftware", str(path))

    def test_vivaldi_dict_paths_empty_when_no_user_data(self):
        with patch.object(paths_mod, "vivaldi_user_data_dir", return_value=Path("/no/vivaldi")):
            self.assertEqual(paths_mod.vivaldi_dict_paths(), [])

    def test_vivaldi_dict_paths_finds_profiles(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "Default").mkdir(parents=True)
            with patch.object(paths_mod, "vivaldi_user_data_dir", return_value=base):
                pairs = paths_mod.vivaldi_dict_paths()
            self.assertEqual(pairs[0][0], "Default")

    def test_vivaldi_user_data_linux(self):
        with (
            patch.object(paths_mod, "is_windows", return_value=False),
            patch.object(paths_mod, "is_macos", return_value=False),
            patch.object(paths_mod, "home_dir", return_value=Path("/home/u")),
        ):
            self.assertEqual(
                paths_mod.vivaldi_user_data_dir(),
                Path("/home/u/.config/vivaldi"),
            )

    def test_chromium_dict_paths_shared(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "Default").mkdir()
            (base / "Other").mkdir()
            pairs = paths_mod._chromium_dict_paths(base)
            self.assertEqual(len(pairs), 1)
            self.assertEqual(pairs[0][0], "Default")


class TestEdgePaths(unittest.TestCase):
    def test_edge_dict_paths_empty_when_no_user_data(self):
        with patch.object(paths_mod, "edge_user_data_dir", return_value=Path("/no/edge")):
            self.assertEqual(paths_mod.edge_dict_paths(), [])

    def test_edge_dict_paths_finds_profiles(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "Default").mkdir(parents=True)
            (base / "Profile 1").mkdir(parents=True)
            with patch.object(paths_mod, "edge_user_data_dir", return_value=base):
                pairs = paths_mod.edge_dict_paths()
            names = [name for name, _ in pairs]
            self.assertIn("Default", names)
            self.assertIn("Profile 1", names)

    def test_edge_user_data_windows(self):
        with (
            patch.object(paths_mod, "is_windows", return_value=True),
            patch.object(paths_mod, "is_macos", return_value=False),
            patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\u\AppData\Local"}, clear=False),
        ):
            path = paths_mod.edge_user_data_dir()
            self.assertIn("Microsoft", str(path))
            self.assertIn("Edge", str(path))

    def test_edge_user_data_macos(self):
        with (
            patch.object(paths_mod, "is_windows", return_value=False),
            patch.object(paths_mod, "is_macos", return_value=True),
            patch.object(paths_mod, "app_support_dir", return_value=Path("/lib/App Support")),
        ):
            self.assertEqual(
                paths_mod.edge_user_data_dir(),
                Path("/lib/App Support/Microsoft Edge"),
            )


class TestLibreOfficePaths(unittest.TestCase):
    def test_libreoffice_dict_paths_only_when_file_exists(self):
        with tempfile.TemporaryDirectory() as d:
            user = Path(d) / "user"
            wordbook = user / "wordbook"
            wordbook.mkdir(parents=True)
            with patch.object(paths_mod, "libreoffice_user_dir", return_value=user):
                self.assertEqual(paths_mod.libreoffice_dict_paths(), [])
            (wordbook / "standard.dic").write_text("word\n", encoding="utf-8")
            with patch.object(paths_mod, "libreoffice_user_dir", return_value=user):
                pairs = paths_mod.libreoffice_dict_paths()
            self.assertEqual(len(pairs), 1)
            self.assertEqual(pairs[0][0], "libreoffice")


if __name__ == "__main__":
    unittest.main(verbosity=2)
