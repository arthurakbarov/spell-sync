import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import spell_sync.settings as settings_mod


class TestSettingsDiagnostics(unittest.TestCase):
    def test_parse_toml_rejects_invalid_syntax(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spell-sync.toml"
            path.write_text(
                'not a section\n[dictionaries]\nchrome = true\nbrave = "maybe"\n',
                encoding="utf-8",
            )
            data, issues = settings_mod._parse_toml_with_issues(path)
            self.assertEqual(data, {})
            self.assertTrue(issues)

    def test_unknown_config_keys_reports_unknowns(self):
        settings = {
            "dictionaries": {"chrome": True, "unknown_dict": False},
            "weird": {"x": True},
        }
        unknown = settings_mod.unknown_config_keys(settings)
        self.assertIn("[dictionaries] unknown_dict: unknown key", unknown)
        self.assertIn("[weird]: unknown section", unknown)

    def test_parse_toml_read_oserror_reports_issue(self):
        path = Path("/nonexistent/spell-sync.toml")
        data, issues = settings_mod._parse_toml_with_issues(path)
        self.assertEqual(data, {})
        self.assertTrue(issues)
        self.assertTrue(any("unreadable" in item for item in issues))
        self.assertFalse(any("/nonexistent/" in item for item in issues))

    def test_parse_toml_malformed_line_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spell-sync.toml"
            path.write_text("[dictionaries]\nchrome\n", encoding="utf-8")
            data, issues = settings_mod._parse_toml_with_issues(path)
            self.assertEqual(data, {})
            self.assertTrue(issues)

    def test_parse_toml_empty_key_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spell-sync.toml"
            path.write_text("[dictionaries]\n = true\n", encoding="utf-8")
            data, issues = settings_mod._parse_toml_with_issues(path)
            self.assertEqual(data, {})
            self.assertTrue(issues)

    def test_parse_toml_duplicate_keys_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spell-sync.toml"
            path.write_text(
                "[push]\nstrict = true\nstrict = false\n",
                encoding="utf-8",
            )
            data, issues = settings_mod._parse_toml_with_issues(path)
            self.assertEqual(data, {})
            self.assertTrue(issues)

    def test_root_scalar_is_invalid_type_issue(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spell-sync.toml"
            path.write_text("orphan = true\n[dictionaries]\nchrome = true\n", encoding="utf-8")
            data, issues = settings_mod._parse_toml_with_issues(path)
            self.assertTrue(data["dictionaries"]["chrome"])
            self.assertTrue(any("must be a table" in i for i in issues))

    def test_all_known_sections_lists_every_section(self):
        sections = set(settings_mod.KNOWN_KEYS.keys())
        self.assertIn("dictionaries", sections)
        self.assertIn("io", sections)

    def test_load_project_settings_with_issues_loads_project_file(self):
        with tempfile.TemporaryDirectory() as d:
            project = Path(d) / "spell-sync.toml"
            project.write_text("[dictionaries]\nchrome = true\n", encoding="utf-8")
            with patch.object(settings_mod, "project_config_path", return_value=project):
                loaded, issues = settings_mod.load_project_settings_with_issues()
            self.assertTrue(loaded["dictionaries"]["chrome"])
            self.assertEqual(issues, [])
