"""Personal workspace Git dirty detection and git-save."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spell_sync.cli_options import CliOptions
from spell_sync.git_save_cmd import cmd_git_save
from spell_sync.workspace_git import (
    commit_personal_workspace,
    inspect_workspace_git,
    workspace_git_dirty_message,
)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def _init_repo(root: Path) -> None:
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    (root / "wordlist.txt").write_text("alpha\n", encoding="utf-8")
    (root / "spell-sync.toml").write_text("[dictionaries]\nsublime = true\n", encoding="utf-8")
    _git(root, "add", "wordlist.txt", "spell-sync.toml")
    _git(root, "commit", "-m", "initial")


class TestWorkspaceGit(unittest.TestCase):
    def test_clean_repo_not_dirty(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _init_repo(root)
            status = inspect_workspace_git(root)
            assert status is not None
            self.assertFalse(status.is_dirty)

    def test_dirty_wordlist_detected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _init_repo(root)
            (root / "wordlist.txt").write_text("alpha\nbeta\n", encoding="utf-8")
            status = inspect_workspace_git(root)
            assert status is not None
            self.assertTrue(status.is_dirty)
            self.assertIn("wordlist.txt", status.dirty_names)
            message = workspace_git_dirty_message(status)
            self.assertIn("git-save", message)

    def test_commit_personal_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _init_repo(root)
            (root / "wordlist.txt").write_text("alpha\nbeta\n", encoding="utf-8")
            status = inspect_workspace_git(root)
            assert status is not None
            ok, detail = commit_personal_workspace(status, message="test update")
            self.assertTrue(ok, detail)
            status2 = inspect_workspace_git(root)
            assert status2 is not None
            self.assertFalse(status2.is_dirty)

    def test_git_save_commit_with_yes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _init_repo(root)
            (root / "wordlist.txt").write_text("alpha\nbeta\n", encoding="utf-8")
            opts = CliOptions(wordlist=str(root / "wordlist.txt"), yes=True)
            code = cmd_git_save(opts)
            self.assertEqual(code, 0)
            status = inspect_workspace_git(root)
            assert status is not None
            self.assertFalse(status.is_dirty)

    def test_non_git_folder(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "wordlist.txt").write_text("alpha\n", encoding="utf-8")
            self.assertIsNone(inspect_workspace_git(root))
            opts = CliOptions(wordlist=str(root / "wordlist.txt"), yes=True)
            self.assertEqual(cmd_git_save(opts), 0)


class TestDoctorGitWarn(unittest.TestCase):
    def test_doctor_warns_when_dirty(self) -> None:
        import spell_sync.doctor as doctor_mod
        from spell_sync.io import write_text_words
        from tests.runtime_helpers import make_sync_run

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _init_repo(root)
            (root / "wordlist.txt").write_text("alpha\nbeta\n", encoding="utf-8")
            write_text_words(root / "wordlist.txt", ["alpha", "beta"], "utf-8", False, quiet=True)
            run = make_sync_run(str(root / "wordlist.txt"), dictionaries=[])
            with patch(
                "spell_sync.health.report.inspect_workspace_git",
                side_effect=lambda _p: inspect_workspace_git(root),
            ):
                report = doctor_mod.build_doctor_report(run)
            messages = [check.message for check in report.checks]
            self.assertTrue(
                any("uncommitted changes" in message for message in messages),
                messages,
            )

    def test_status_detail_warns_when_dirty(self) -> None:
        from spell_sync.application.builders import build_status_detail_snapshot
        from spell_sync.io import write_text_words
        from tests.runtime_helpers import make_sync_run

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _init_repo(root)
            write_text_words(root / "wordlist.txt", ["alpha", "beta"], "utf-8", False, quiet=True)
            run = make_sync_run(str(root / "wordlist.txt"), dictionaries=[])
            with patch(
                "spell_sync.application.builders.inspect_workspace_git",
                side_effect=lambda _p: inspect_workspace_git(root),
            ):
                detail = build_status_detail_snapshot(run)
            self.assertTrue(
                any("uncommitted changes" in warning for warning in detail.warnings),
                detail.warnings,
            )
            self.assertTrue(
                any("git-save" in warning for warning in detail.warnings),
                detail.warnings,
            )


class TestGitSaveEdges(unittest.TestCase):
    def test_git_save_requires_yes_when_noninteractive(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _init_repo(root)
            (root / "wordlist.txt").write_text("alpha\nbeta\n", encoding="utf-8")
            opts = CliOptions(wordlist=str(root / "wordlist.txt"), yes=False, json_output=True)
            code = cmd_git_save(opts)
            self.assertNotEqual(code, 0)
            status = inspect_workspace_git(root)
            assert status is not None
            self.assertTrue(status.is_dirty)

    def test_git_save_surfaces_hook_failure(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _init_repo(root)
            hooks = root / ".git" / "hooks"
            hooks.mkdir(parents=True, exist_ok=True)
            pre_commit = hooks / "pre-commit"
            pre_commit.write_text("#!/bin/sh\necho hook-blocked >&2\nexit 1\n", encoding="utf-8")
            pre_commit.chmod(0o755)
            (root / "wordlist.txt").write_text("alpha\nbeta\n", encoding="utf-8")
            opts = CliOptions(wordlist=str(root / "wordlist.txt"), yes=True)
            code = cmd_git_save(opts)
            self.assertNotEqual(code, 0)
            status = inspect_workspace_git(root)
            assert status is not None
            self.assertTrue(status.is_dirty)

    def test_commit_ignores_untracked_noise_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _init_repo(root)
            (root / "notes.md").write_text("noise\n", encoding="utf-8")
            status = inspect_workspace_git(root)
            assert status is not None
            self.assertFalse(status.is_dirty)

    def test_nested_project_dirty_uses_relative_pathspecs(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _git(root, "init")
            _git(root, "config", "user.email", "test@example.com")
            _git(root, "config", "user.name", "Test")
            nested = root / "personal"
            nested.mkdir()
            (nested / "wordlist.txt").write_text("alpha\n", encoding="utf-8")
            (nested / "spell-sync.toml").write_text(
                "[dictionaries]\nsublime = true\n", encoding="utf-8"
            )
            _git(root, "add", "personal/wordlist.txt", "personal/spell-sync.toml")
            _git(root, "commit", "-m", "initial")
            (nested / "wordlist.txt").write_text("alpha\nbeta\n", encoding="utf-8")
            status = inspect_workspace_git(nested)
            assert status is not None
            self.assertTrue(status.is_dirty)
            self.assertEqual(status.dirty_relpaths, ("personal/wordlist.txt",))

    def test_commit_pathspecs_exclude_unrelated_staged_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _init_repo(root)
            (root / "notes.md").write_text("tracked later\n", encoding="utf-8")
            _git(root, "add", "notes.md")
            (root / "wordlist.txt").write_text("alpha\nbeta\n", encoding="utf-8")
            status = inspect_workspace_git(root)
            assert status is not None
            ok, detail = commit_personal_workspace(status, message="personal only")
            self.assertTrue(ok, detail)
            # Unrelated staged notes.md must remain staged / uncommitted.
            porcelain = subprocess.run(
                ["git", "status", "--porcelain", "--", "notes.md"],
                cwd=str(root),
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            self.assertTrue(porcelain.strip().startswith("A "), porcelain)
            status2 = inspect_workspace_git(root)
            assert status2 is not None
            self.assertFalse(status2.is_dirty)

    def test_git_save_json_error_envelope(self) -> None:
        import io
        import json
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _init_repo(root)
            (root / "wordlist.txt").write_text("alpha\nbeta\n", encoding="utf-8")
            opts = CliOptions(wordlist=str(root / "wordlist.txt"), yes=False, json_output=True)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cmd_git_save(opts)
            self.assertNotEqual(code, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["command"], "git-save")
            self.assertIn("exit", payload)
            self.assertTrue(payload["dirty"])
            self.assertFalse(payload["committed"])


if __name__ == "__main__":
    unittest.main()
