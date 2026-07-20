"""End-to-end workflow using an installed wheel outside the source tree."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from spell_sync.config import EDITOR_DICT_FILENAME
from spell_sync.paths import is_macos
from tests.journal_test_utils import write_test_journal


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _editor_dictionary(home: Path) -> Path:
    if is_macos():
        base = home / "Library" / "Application Support"
    else:
        base = home / ".config"
    user_path = base / "Cursor" / "User"
    user_path.mkdir(parents=True, exist_ok=True)
    return user_path / EDITOR_DICT_FILENAME


@pytest.fixture(scope="module")
def installed_spell_sync(tmp_path_factory):
    root = _repo_root()
    build_dir = tmp_path_factory.mktemp("wheel-build")
    subprocess.run(
        [sys.executable, "-m", "build", "-w", "-n", "--outdir", str(build_dir)],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    wheels = list(build_dir.glob("*.whl"))
    assert wheels, "wheel build produced no artifact"
    venv_dir = tmp_path_factory.mktemp("wheel-venv")
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    venv_python = venv_dir / "bin" / "python"
    if not venv_python.is_file():
        venv_python = venv_dir / "Scripts" / "python.exe"
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", "-q", str(wheels[0])],
        check=True,
    )
    return venv_python


def _run(
    venv_python: Path,
    *,
    home: Path,
    cwd: Path,
    args: list[str],
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    if not is_macos():
        env["XDG_CONFIG_HOME"] = str(home / ".config")
    return subprocess.run(
        [str(venv_python), "-m", "spell_sync", *args],
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _history_file(venv_python: Path, home: Path) -> Path | None:
    env = os.environ.copy()
    env["HOME"] = str(home)
    if not is_macos():
        env["XDG_CONFIG_HOME"] = str(home / ".config")
    result = subprocess.run(
        [
            str(venv_python),
            "-c",
            "from spell_sync.diagnostics.paths import resolve_app_state_paths; "
            "print(resolve_app_state_paths().history_file)",
        ],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    path = Path(result.stdout.strip())
    return path if path.is_file() else None


def test_installed_wheel_full_workflow(installed_spell_sync, tmp_path: Path) -> None:
    venv_python = installed_spell_sync
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    outside_repo = tmp_path / "outside"
    outside_repo.mkdir()

    help_result = _run(venv_python, home=home, cwd=outside_repo, args=["--help"])
    assert help_result.returncode == 0
    assert "pull" in help_result.stdout.lower()

    version_result = _run(venv_python, home=home, cwd=outside_repo, args=["version"])
    assert version_result.returncode == 0
    assert "0.2.1" in version_result.stdout

    init_result = _run(
        venv_python,
        home=home,
        cwd=project,
        args=["init", "-C", str(project / "wordlist.txt")],
    )
    assert init_result.returncode == 0, init_result.stderr
    wordlist = project / "wordlist.txt"
    assert wordlist.is_file()
    config = project / "spell-sync.toml"
    config.write_text(
        config.read_text(encoding="utf-8").replace("editors = false", "editors = true"),
        encoding="utf-8",
    )

    editor_dict = _editor_dictionary(home)
    editor_dict.parent.mkdir(parents=True, exist_ok=True)
    editor_dict.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    wordlist.write_text("alpha\nbeta\n", encoding="utf-8")

    status_result = _run(
        venv_python,
        home=home,
        cwd=project,
        args=["status", "-C", str(wordlist), "--json"],
    )
    assert status_result.returncode == 0, status_result.stderr
    status_payload = json.loads(status_result.stdout)
    assert status_payload["command"] == "status"

    pull_result = _run(
        venv_python,
        home=home,
        cwd=project,
        args=["pull", "-C", str(wordlist), "--json"],
    )
    assert pull_result.returncode == 0, pull_result.stderr
    assert "gamma" in wordlist.read_text(encoding="utf-8")

    push_result = _run(
        venv_python,
        home=home,
        cwd=project,
        args=["push", "-C", str(wordlist), "-y", "--json"],
    )
    assert push_result.returncode == 0, push_result.stderr
    assert "gamma" in editor_dict.read_text(encoding="utf-8")

    write_test_journal(wordlist)
    recover_result = _run(
        venv_python,
        home=home,
        cwd=project,
        args=["recover", "-C", str(wordlist), "-y", "--json"],
    )
    assert recover_result.returncode == 0, recover_result.stderr

    second_launch = _run(
        venv_python,
        home=home,
        cwd=project,
        args=["status", "-C", str(wordlist), "--json"],
    )
    assert second_launch.returncode == 0, second_launch.stderr

    history_file = _history_file(venv_python, home)
    if history_file is not None:
        history_text = history_file.read_text(encoding="utf-8")
        assert "gamma" not in history_text
        assert str(editor_dict.resolve()) not in history_text

    support_result = _run(
        venv_python,
        home=home,
        cwd=outside_repo,
        args=["support-report", "-C", str(wordlist), "--format", "json"],
    )
    assert support_result.returncode == 0, support_result.stderr
    assert "secret-token-like-value" not in support_result.stdout
    assert "user@example.com" not in support_result.stdout

    bundled_env = os.environ.copy()
    bundled_env["HOME"] = str(home)
    if not is_macos():
        bundled_env["XDG_CONFIG_HOME"] = str(home / ".config")
    bundled_check = subprocess.run(
        [
            str(venv_python),
            "-c",
            "from importlib.resources import files; "
            "path = files('spell_sync.bundled').joinpath('target-validation.json'); "
            "assert path.is_file(), path; "
            "from spell_sync.target_validation import load_packaged_target_validation; "
            "payload = load_packaged_target_validation(); "
            "assert payload is not None; "
            "import platform; "
            "current = {'Darwin': 'macos', 'Windows': 'windows'}.get(platform.system(), 'linux'); "
            "chrome = next("
            "row for row in payload['targets'] "
            "if row['target_id'] == 'chrome' and row['platform'] == current"
            "); "
            "assert chrome['automated_validation'] == 'pass'; "
            "assert chrome['manual_validation'] == 'not-run'",
        ],
        env=bundled_env,
        capture_output=True,
        text=True,
    )
    assert bundled_check.returncode == 0, bundled_check.stderr
