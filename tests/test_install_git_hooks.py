"""Tests for opt-in commit-msg hook installer."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import install_git_hooks  # noqa: E402


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "README").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=ci@test", "-c", "user.name=ci", "add", "-A"],
        cwd=path,
        check=True,
    )
    subprocess.run(
        ["git", "-c", "user.email=ci@test", "-c", "user.name=ci", "commit", "-qm", "Init."],
        cwd=path,
        check=True,
    )


def test_install_status_remove_roundtrip(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    assert install_git_hooks.main(["status", "--repo", str(repo)]) == 0
    assert install_git_hooks.main(["install", "--repo", str(repo)]) == 0
    hook = repo / ".git" / "hooks" / "commit-msg"
    assert hook.is_file()
    assert install_git_hooks.MARKER in hook.read_text(encoding="utf-8")
    assert install_git_hooks.main(["status", "--repo", str(repo)]) == 0
    assert install_git_hooks.main(["remove", "--repo", str(repo)]) == 0
    assert not hook.exists()


def test_refuses_unmanaged_hook_without_force(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    hook = repo / ".git" / "hooks" / "commit-msg"
    hook.write_text("#!/bin/sh\necho unmanaged\n", encoding="utf-8")
    assert install_git_hooks.main(["install", "--repo", str(repo)]) == 2
    assert install_git_hooks.main(["install", "--repo", str(repo), "--force"]) == 0
    assert install_git_hooks.MARKER in hook.read_text(encoding="utf-8")


def test_validate_commit_messages_message_file(tmp_path: Path) -> None:
    good = tmp_path / "good.txt"
    good.write_text("Harden commit hooks.\n", encoding="utf-8")
    bad = tmp_path / "bad.txt"
    bad.write_text("feat: missing period\n", encoding="utf-8")
    good_rc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate_commit_messages.py"),
            "--message-file",
            str(good),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    bad_rc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate_commit_messages.py"),
            "--message-file",
            str(bad),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert good_rc.returncode == 0, good_rc.stdout + good_rc.stderr
    assert bad_rc.returncode != 0
