#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Neovim mkspell after push."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import spell_sync.neovim_mkspell as mkspell_mod


class TestNeovimMkspell(unittest.TestCase):
    def test_skips_when_nvim_missing(self):
        with patch.object(mkspell_mod.shutil, "which", return_value=None):
            self.assertFalse(mkspell_mod.run_mkspell_for_add_file(Path("/tmp/x.add")))

    def test_runs_nvim_headless(self):
        with tempfile.TemporaryDirectory() as d:
            add_path = Path(d) / "en.utf-8.add"
            add_path.write_text("alpha\n", encoding="utf-8")
            spl_path = add_path.with_suffix(".spl")
            spl_path.write_text("spl", encoding="utf-8")
            fake = MagicMock(returncode=0, stdout="", stderr="")
            with (
                patch.object(mkspell_mod.shutil, "which", return_value="/usr/bin/nvim"),
                patch.object(mkspell_mod.subprocess, "run", return_value=fake) as run,
            ):
                self.assertTrue(mkspell_mod.run_mkspell_for_add_file(add_path))
            self.assertIn("mkspell", run.call_args[0][0][3])
            self.assertIn("fnameescape", run.call_args[0][0][3])

    def test_mkspell_after_neovim_writes_disabled(self):
        with patch("spell_sync.config.neovim_mkspell_after_push", return_value=False):
            with patch.object(mkspell_mod, "run_mkspell_for_add_file") as run:
                mkspell_mod.mkspell_after_neovim_writes(("nvim-en",))
            run.assert_not_called()


class TestMkspellAfterPush(unittest.TestCase):
    def test_mkspell_after_neovim_writes_skips_when_disabled(self):
        with patch(
            "spell_sync.config.neovim_mkspell_after_push",
            return_value=False,
        ):
            with patch.object(mkspell_mod, "run_mkspell_for_add_file") as mkspell:
                mkspell_mod.mkspell_after_neovim_writes(("nvim-en",))
            mkspell.assert_not_called()

    def test_mkspell_after_neovim_writes_runs_for_nvim_dict(self):
        add_path = Path("/tmp/nvim-en.utf-8.add")
        with (
            patch(
                "spell_sync.config.neovim_mkspell_after_push",
                return_value=True,
            ),
            patch(
                "spell_sync.paths.neovim_dict_paths",
                return_value=[("nvim-en", add_path)],
            ),
            patch.object(mkspell_mod, "run_mkspell_for_add_file", return_value=True) as mkspell,
        ):
            mkspell_mod.mkspell_after_neovim_writes(("nvim-en",))
        mkspell.assert_called_once_with(add_path)

    def test_mkspell_after_skips_non_nvim_names(self):
        with (
            patch(
                "spell_sync.config.neovim_mkspell_after_push",
                return_value=True,
            ),
            patch.object(mkspell_mod, "run_mkspell_for_add_file") as mkspell,
        ):
            mkspell_mod.mkspell_after_neovim_writes(("chrome:Default",))
        mkspell.assert_not_called()

    def test_run_mkspell_success(self):
        with tempfile.TemporaryDirectory() as d:
            add_path = Path(d) / "en.utf-8.add"
            add_path.write_text("word\n", encoding="utf-8")
            spl_path = add_path.with_suffix(".spl")

            def fake_run(cmd, **kwargs):
                spl_path.write_text("spl", encoding="utf-8")
                return MagicMock(returncode=0, stdout="", stderr="")

            with (
                patch.object(mkspell_mod.shutil, "which", return_value="/usr/bin/nvim"),
                patch.object(mkspell_mod.subprocess, "run", side_effect=fake_run),
            ):
                self.assertTrue(mkspell_mod.run_mkspell_for_add_file(add_path))

    def test_run_mkspell_missing_add_file(self):
        with patch.object(mkspell_mod.shutil, "which", return_value="/usr/bin/nvim"):
            self.assertFalse(mkspell_mod.run_mkspell_for_add_file(Path("/missing.add")))

    def test_vim_single_quote_escapes_apostrophe(self):
        self.assertEqual(mkspell_mod._vim_single_quote("it's"), "'it''s'")

    def test_run_mkspell_subprocess_oserror(self):
        with tempfile.TemporaryDirectory() as d:
            add_path = Path(d) / "en.utf-8.add"
            add_path.write_text("word\n", encoding="utf-8")
            with (
                patch.object(mkspell_mod.shutil, "which", return_value="/usr/bin/nvim"),
                patch.object(
                    mkspell_mod.subprocess,
                    "run",
                    side_effect=OSError("spawn failed"),
                ),
            ):
                self.assertFalse(mkspell_mod.run_mkspell_for_add_file(add_path))

    def test_run_mkspell_timeout(self):
        with tempfile.TemporaryDirectory() as d:
            add_path = Path(d) / "en.utf-8.add"
            add_path.write_text("word\n", encoding="utf-8")
            with (
                patch.object(mkspell_mod.shutil, "which", return_value="/usr/bin/nvim"),
                patch.object(
                    mkspell_mod.subprocess,
                    "run",
                    side_effect=subprocess.TimeoutExpired(cmd="nvim", timeout=60),
                ),
            ):
                self.assertFalse(mkspell_mod.run_mkspell_for_add_file(add_path))

    def test_run_mkspell_nonzero_exit_uses_stderr(self):
        with tempfile.TemporaryDirectory() as d:
            add_path = Path(d) / "en.utf-8.add"
            add_path.write_text("word\n", encoding="utf-8")
            fake = MagicMock(returncode=1, stdout="", stderr="bad mkspell")
            with (
                patch.object(mkspell_mod.shutil, "which", return_value="/usr/bin/nvim"),
                patch.object(mkspell_mod.subprocess, "run", return_value=fake),
            ):
                self.assertFalse(mkspell_mod.run_mkspell_for_add_file(add_path))

    def test_run_mkspell_nonzero_exit_falls_back_to_stdout(self):
        with tempfile.TemporaryDirectory() as d:
            add_path = Path(d) / "en.utf-8.add"
            add_path.write_text("word\n", encoding="utf-8")
            fake = MagicMock(returncode=2, stdout="stdout detail", stderr="")
            with (
                patch.object(mkspell_mod.shutil, "which", return_value="/usr/bin/nvim"),
                patch.object(mkspell_mod.subprocess, "run", return_value=fake),
            ):
                self.assertFalse(mkspell_mod.run_mkspell_for_add_file(add_path))

    def test_run_mkspell_success_without_spl_file(self):
        with tempfile.TemporaryDirectory() as d:
            add_path = Path(d) / "en.utf-8.add"
            add_path.write_text("word\n", encoding="utf-8")
            fake = MagicMock(returncode=0, stdout="", stderr="")
            with (
                patch.object(mkspell_mod.shutil, "which", return_value="/usr/bin/nvim"),
                patch.object(mkspell_mod.subprocess, "run", return_value=fake),
            ):
                self.assertFalse(mkspell_mod.run_mkspell_for_add_file(add_path))


if __name__ == "__main__":
    import unittest

    unittest.main(verbosity=2)
