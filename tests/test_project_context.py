"""CLI project paths follow the effective ``-C`` wordlist."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from spell_sync.cli_options import CliOptions
from spell_sync.commands import cmd_init
from spell_sync.config_check_cmd import cmd_config_check
from spell_sync.project import ProjectContext
from spell_sync.settings import bind_active_settings, load_user_settings_with_issues
from spell_sync.sync_context import RuntimeContext, runtime_context_for

_ROOT = Path(__file__).resolve().parent.parent


def _run_from(
    cwd: Path,
    home: Path,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["PYTHONPATH"] = str(_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "spell_sync", *args],
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_project_context_uses_resolved_wordlist_parent(tmp_path: Path) -> None:
    wordlist = tmp_path / "project" / "wordlist.txt"
    context = ProjectContext.build(wordlist)
    assert context.wordlist == wordlist
    assert context.project_dir == wordlist.resolve().parent
    assert context.config_paths[-1] == context.project_dir / "spell-sync.toml"


def test_scoped_settings_and_runtime_reuse_validated_context(tmp_path: Path) -> None:
    bind_active_settings({"push": {"strict": True}})
    settings, issues = load_user_settings_with_issues()
    assert settings == {"push": {"strict": True}}
    assert issues == []

    context = RuntimeContext.build(tmp_path / "wordlist.txt", dictionaries=[])
    validated = SimpleNamespace(context=context)
    with patch("spell_sync.command_helpers.active_validated_runtime", return_value=validated):
        assert runtime_context_for(CliOptions()) is context


def test_human_config_check_lists_explicit_project_config(tmp_path: Path) -> None:
    wordlist = tmp_path / "wordlist.txt"
    wordlist.write_text("alpha\n", encoding="utf-8")
    config = tmp_path / "spell-sync.toml"
    config.write_text("[push]\nstrict = true\n", encoding="utf-8")
    output = StringIO()
    with redirect_stdout(output):
        code = cmd_config_check(CliOptions(wordlist=str(wordlist)))
    assert code == 0
    assert str(config) in output.getvalue()


def test_human_config_check_warns_when_no_toml(tmp_path: Path, monkeypatch) -> None:
    wordlist = tmp_path / "wordlist.txt"
    wordlist.write_text("alpha\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))
    (tmp_path / "empty-home").mkdir()
    output = StringIO()
    with redirect_stdout(output):
        code = cmd_config_check(CliOptions(wordlist=str(wordlist)))
    assert code == 0
    assert "no spell-sync.toml found" in output.getvalue()


def test_init_with_explicit_wordlist_uses_its_project(tmp_path: Path) -> None:
    wordlist = tmp_path / "nested" / "wordlist.txt"
    wordlist.parent.mkdir()
    code = cmd_init(CliOptions(wordlist=str(wordlist)))
    assert code == 0
    assert wordlist.is_file()


def test_config_check_uses_explicit_wordlist_project(tmp_path: Path) -> None:
    project = tmp_path / "project"
    other = tmp_path / "other"
    home = tmp_path / "home"
    project.mkdir()
    other.mkdir()
    home.mkdir()
    wordlist = project / "wordlist.txt"
    wordlist.write_text("alpha\n", encoding="utf-8")
    config = project / "spell-sync.toml"
    config.write_text("[dictionaries\nchrome = true\n", encoding="utf-8")

    result = _run_from(other, home, "config-check", "-C", str(wordlist), "--json")

    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["paths"] == [str(config)]
    assert any(str(config) in issue for issue in payload["issues"])
    assert any(
        "line" in issue.lower() or "end of document" in issue.lower() for issue in payload["issues"]
    )


def test_doctor_ignores_hooks_in_other_cwd_repo(tmp_path: Path) -> None:
    wordlist_repo = tmp_path / "wordlist-repo"
    other_repo = tmp_path / "other-repo"
    home = tmp_path / "home"
    wordlist_repo.mkdir()
    other_repo.mkdir()
    home.mkdir()
    wordlist = wordlist_repo / "wordlist.txt"
    wordlist.write_text("alpha\n", encoding="utf-8")
    (wordlist_repo / "spell-sync.toml").write_text(
        "[dictionaries]\n"
        "editors = false\nchrome = false\nedge = false\nbrave = false\nvivaldi = false\n"
        "firefox = false\nneovim = false\njetbrains = false\nhunspell = false\n"
        "obsidian = false\nlibreoffice = false\n",
        encoding="utf-8",
    )
    hooks = other_repo / ".git" / "hooks"
    hooks.mkdir(parents=True)
    for name in ("pre-push", "pre-commit"):
        (hooks / name).write_text("#!/bin/sh\n# show-toplevel\n", encoding="utf-8")

    result = _run_from(other_repo, home, "doctor", "-C", str(wordlist), "--json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["git_hooks"] is None
    rendered = json.dumps(payload)
    assert "scripts/install-hooks.sh" not in rendered
    assert str(other_repo) not in rendered
