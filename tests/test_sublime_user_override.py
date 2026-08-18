"""Sublime User Preferences override detection."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import spell_sync.doctor as doctor_mod
import spell_sync.sublime_preferences as sublime_prefs
from spell_sync.io import write_text_words
from tests.runtime_helpers import make_sync_run


class TestSublimeUserOverride(unittest.TestCase):
    def test_missing_user_prefs_is_no_override(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            packages = Path(raw)
            self.assertEqual(
                sublime_prefs.user_added_words_override_count(packages_dir=packages),
                0,
            )
            self.assertIsNone(
                sublime_prefs.user_added_words_override_message(packages_dir=packages),
            )

    def test_empty_added_words_key_is_override(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            packages = Path(raw)
            user = packages / "User"
            user.mkdir()
            path = user / "Preferences.sublime-settings"
            path.write_text('{"spell_check": true}\n', encoding="utf-8")
            self.assertEqual(
                sublime_prefs.user_added_words_override_count(packages_dir=packages),
                0,
            )
            path.write_text('{"added_words": []}\n', encoding="utf-8")
            self.assertEqual(
                sublime_prefs.user_added_words_override_count(packages_dir=packages),
                -1,
            )
            message = sublime_prefs.user_added_words_override_message(packages_dir=packages)
            assert message is not None
            self.assertIn("added_words (empty)", message)
            self.assertIn("overrides the SpellSync package", message)

    def test_non_empty_added_words_is_override(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            packages = Path(raw)
            user = packages / "User"
            user.mkdir()
            path = user / "Preferences.sublime-settings"
            path.write_text(
                json.dumps({"spell_check": True, "added_words": ["Alpha", "beta"]}) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(
                sublime_prefs.user_added_words_override_count(packages_dir=packages),
                2,
            )
            message = sublime_prefs.user_added_words_override_message(packages_dir=packages)
            assert message is not None
            self.assertIn("overrides the SpellSync package", message)
            self.assertIn("2", message)

    def test_relaxed_json_with_comments_and_trailing_comma(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            packages = Path(raw)
            user = packages / "User"
            user.mkdir()
            path = user / "Preferences.sublime-settings"
            path.write_text(
                '{\n  // comment\n  "added_words": ["one", "two",],\n}\n',
                encoding="utf-8",
            )
            self.assertEqual(
                sublime_prefs.user_added_words_override_count(packages_dir=packages),
                2,
            )

    def test_urls_inside_strings_survive_jsonc_strip(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            packages = Path(raw)
            user = packages / "User"
            user.mkdir()
            path = user / "Preferences.sublime-settings"
            path.write_text(
                "{\n"
                "  // note\n"
                '  "update_check_url": "https://example.com/check",\n'
                '  "added_words": ["Alpha"],\n'
                "}\n",
                encoding="utf-8",
            )
            self.assertEqual(
                sublime_prefs.user_added_words_override_count(packages_dir=packages),
                1,
            )

    def test_doctor_warns_when_user_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            wordlist = root / "wordlist.txt"
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            packages = root / "Packages"
            user = packages / "User"
            user.mkdir(parents=True)
            (user / "Preferences.sublime-settings").write_text(
                json.dumps({"added_words": ["stale"]}) + "\n",
                encoding="utf-8",
            )
            run = make_sync_run(str(wordlist), dictionaries=[])
            with (
                patch.object(
                    sublime_prefs,
                    "sublime_packages_dir",
                    return_value=packages,
                ),
                patch("spell_sync.dictionary_hints.enable_sublime", return_value=True),
                patch("spell_sync.dictionary_hints.sublime_text_installed", return_value=True),
                patch("spell_sync.dictionary_hints.enable_editors", return_value=False),
                patch(
                    "spell_sync.dictionary_hints.user_added_words_override_message",
                    side_effect=lambda: sublime_prefs.user_added_words_override_message(
                        packages_dir=packages,
                    ),
                ),
            ):
                report = doctor_mod.build_doctor_report(run)
            messages = [check.message for check in report.checks]
            self.assertTrue(
                any("overrides the SpellSync package" in message for message in messages),
                messages,
            )

    def test_doctor_silent_when_user_has_no_added_words(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            wordlist = root / "wordlist.txt"
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            packages = root / "Packages"
            user = packages / "User"
            user.mkdir(parents=True)
            (user / "Preferences.sublime-settings").write_text(
                '{"spell_check": true}\n',
                encoding="utf-8",
            )
            run = make_sync_run(str(wordlist), dictionaries=[])
            with (
                patch("spell_sync.dictionary_hints.enable_sublime", return_value=True),
                patch("spell_sync.dictionary_hints.sublime_text_installed", return_value=True),
                patch("spell_sync.dictionary_hints.enable_editors", return_value=False),
                patch(
                    "spell_sync.dictionary_hints.user_added_words_override_message",
                    side_effect=lambda: sublime_prefs.user_added_words_override_message(
                        packages_dir=packages,
                    ),
                ),
            ):
                report = doctor_mod.build_doctor_report(run)
            messages = [check.message for check in report.checks]
            self.assertFalse(
                any("overrides the SpellSync package" in message for message in messages),
                messages,
            )

    def test_doctor_warns_when_sublime_missing(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            wordlist = root / "wordlist.txt"
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            run = make_sync_run(str(wordlist), dictionaries=[])
            with (
                patch("spell_sync.dictionary_hints.enable_sublime", return_value=True),
                patch("spell_sync.dictionary_hints.sublime_text_installed", return_value=False),
                patch("spell_sync.dictionary_hints.enable_editors", return_value=False),
            ):
                report = doctor_mod.build_doctor_report(run)
            messages = [check.message for check in report.checks]
            self.assertTrue(
                any("Sublime Text not found" in message for message in messages),
                messages,
            )

    def test_non_string_added_words_entries_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            packages = Path(raw)
            user = packages / "User"
            user.mkdir()
            path = user / "Preferences.sublime-settings"
            path.write_text(
                json.dumps({"added_words": ["keep", 1, None, " ", {"x": 1}]}) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(
                sublime_prefs.user_added_words_override_count(packages_dir=packages),
                1,
            )

    def test_status_detail_warns_on_user_override(self) -> None:
        from spell_sync.application.dashboard_builders import build_status_detail_snapshot
        from spell_sync.dictionaries import Dictionary, DictionaryFormat

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            wordlist = root / "wordlist.txt"
            write_text_words(wordlist, ["alpha"], "utf-8", False, quiet=True)
            packages = root / "Packages"
            spell = packages / "SpellSync"
            user = packages / "User"
            spell.mkdir(parents=True)
            user.mkdir(parents=True)
            spell_path = spell / "Preferences.sublime-settings"
            spell_path.write_text(
                json.dumps({"added_words": ["alpha"]}) + "\n",
                encoding="utf-8",
            )
            (user / "Preferences.sublime-settings").write_text(
                json.dumps({"added_words": ["stale"]}) + "\n",
                encoding="utf-8",
            )
            dictionary = Dictionary("sublime", str(spell_path), DictionaryFormat.JSON)
            run = make_sync_run(str(wordlist), dictionaries=[dictionary])
            with (
                patch(
                    "spell_sync.dictionary_hints.sublime_text_installed",
                    return_value=True,
                ),
                patch(
                    "spell_sync.dictionary_hints.enable_sublime",
                    return_value=True,
                ),
                patch(
                    "spell_sync.dictionary_hints.user_added_words_override_message",
                    side_effect=lambda: sublime_prefs.user_added_words_override_message(
                        packages_dir=packages,
                    ),
                ),
            ):
                detail = build_status_detail_snapshot(run)
            self.assertTrue(
                any("overrides the SpellSync package" in warning for warning in detail.warnings),
                detail.warnings,
            )
            # SpellSync dictionary itself can still report synced — warning is the honesty signal.
            self.assertEqual(detail.targets[0].name, "sublime")

    def test_push_hint_warns_on_user_override(self) -> None:
        import io
        from contextlib import redirect_stdout

        import spell_sync.dictionary_hints as hints_mod
        from spell_sync.runtime_settings import RuntimeSettings

        with tempfile.TemporaryDirectory() as raw:
            packages = Path(raw)
            user = packages / "User"
            user.mkdir()
            (user / "Preferences.sublime-settings").write_text(
                json.dumps({"added_words": ["stale"]}) + "\n",
                encoding="utf-8",
            )
            buf = io.StringIO()
            with (
                patch.object(hints_mod, "sublime_text_installed", return_value=True),
                patch.object(hints_mod, "enable_sublime", return_value=True),
                patch.object(hints_mod, "enable_editors", return_value=False),
                patch.object(hints_mod, "enable_chrome", return_value=False),
                patch.object(hints_mod, "enable_edge", return_value=False),
                patch.object(hints_mod, "enable_brave", return_value=False),
                patch.object(hints_mod, "enable_vivaldi", return_value=False),
                patch.object(hints_mod, "enable_firefox", return_value=False),
                patch.object(hints_mod, "enable_jetbrains", return_value=False),
                patch.object(hints_mod, "enable_hunspell", return_value=False),
                patch.object(hints_mod, "enable_obsidian", return_value=False),
                patch(
                    "spell_sync.dictionary_hints.user_added_words_override_message",
                    side_effect=lambda: sublime_prefs.user_added_words_override_message(
                        packages_dir=packages,
                    ),
                ),
                redirect_stdout(buf),
            ):
                for message in hints_mod.optional_app_warn_messages(
                    settings=RuntimeSettings.defaults()
                ):
                    hints_mod.log.warn(message)
            self.assertIn("overrides the SpellSync package", buf.getvalue())

    def test_sublime_discover_path_is_spell_sync_package_not_user(self) -> None:
        from spell_sync import dictionaries as dictionaries_mod
        from spell_sync.config import SUBLIME_PACKAGE

        with tempfile.TemporaryDirectory() as raw:
            packages = Path(raw)
            with patch.object(dictionaries_mod, "sublime_packages_dir", return_value=packages):
                found = dictionaries_mod._discover_sublime()
            self.assertEqual(len(found), 1)
            path = Path(found[0].path)
            self.assertEqual(path.parent.name, SUBLIME_PACKAGE)
            self.assertNotEqual(path.parent.name, "User")
            self.assertEqual(path.name, "Preferences.sublime-settings")


if __name__ == "__main__":
    unittest.main()
