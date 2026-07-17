#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Additional lint.py coverage."""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import spell_sync.lint as lint_mod
from spell_sync.exit_codes import ExitCode


class TestLintCoverage(unittest.TestCase):
    def test_load_wordlist_lines_oserror(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wordlist.txt"
            path.write_text("alpha\n", encoding="utf-8")
            with patch("builtins.open", side_effect=OSError("read fail")):
                self.assertIsNone(lint_mod.load_wordlist_lines(path))

    def test_print_report_with_many_issues(self):
        words = ["bad word", "bad word", "a", "12", "-x", "Ab", "ab"]
        report = lint_mod.analyze_words(words)
        buf = io.StringIO()
        with redirect_stdout(buf):
            hard, soft = lint_mod.print_report(report, sample=1)
        self.assertGreater(hard, 0)
        self.assertGreater(soft, 0)
        self.assertIn("… and", buf.getvalue())

    def test_run_lint_strict_soft_fails(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wordlist.txt"
            path.write_text("прокcи\n", encoding="utf-8")
            code = lint_mod.run_lint(path, strict=True)
            self.assertEqual(code, ExitCode.LINT_FAILED)

    def test_run_lint_fix_success(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wordlist.txt"
            path.write_text("  alpha  \nalpha\n", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = lint_mod.run_lint(path, fix=True)
            self.assertEqual(code, ExitCode.OK)
            self.assertIn("[fix ]", buf.getvalue())
            self.assertEqual(path.read_text(encoding="utf-8"), "alpha\n")


class TestLintWordlistHelpers(unittest.TestCase):
    def test_load_wordlist_lines_skips_comments(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wordlist.txt"
            path.write_text("# note\nalpha\n", encoding="utf-8")
            self.assertEqual(lint_mod.load_wordlist_lines(path), ["alpha"])

    def test_report_counts_and_clean_lint(self):
        report = lint_mod.LintReport(hard_junk=["x"], unsorted=True, homoglyphs=["прокcи"])
        hard, soft = lint_mod.print_report(report)
        self.assertEqual(hard, 2)
        self.assertEqual(soft, 1)

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wordlist.txt"
            path.write_text("ok\n", encoding="utf-8")
            code = lint_mod.run_lint(path)
            self.assertEqual(code, ExitCode.OK)

    def test_show_case_dupes_truncates_sample(self):
        groups = [[f"a{i}", f"A{i}"] for i in range(5)]
        buf = io.StringIO()
        with redirect_stdout(buf):
            lint_mod._show_case_dupes(groups, sample=2)
        self.assertIn("… and", buf.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
