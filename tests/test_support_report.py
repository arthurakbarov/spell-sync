"""Support report export and privacy tests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from spell_sync.application.service import SpellSyncService
from spell_sync.application.support_report import (
    build_support_report,
    default_support_report_path,
    export_support_report,
    format_support_report_text,
    support_report_to_dict,
)
from spell_sync.cli_options import CliOptions
from spell_sync.diagnostics.paths import resolve_app_state_paths
from spell_sync.paths import is_macos
from spell_sync.support.path_redaction import redact_path, redact_text
from spell_sync.support_report_cmd import cmd_support_report

_ROOT = Path(__file__).resolve().parents[1]
ADVERSARIAL = (
    "personal-project-name",
    "user@example.com",
    "secret-token-like-value",
    "private-name",
)


def _configure_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    if not is_macos():
        monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    return home


def _write_project(home: Path) -> tuple[Path, Path]:
    project = home / "personal-project-name"
    project.mkdir(parents=True)
    wordlist = project / "wordlist.txt"
    wordlist.write_text(
        "secret-token-like-value\nuser@example.com\nalpha\n",
        encoding="utf-8",
    )
    example = _ROOT / "spell_sync" / "bundled" / "spell-sync.toml.example"
    shutil.copy(example, project / "spell-sync.toml")
    return project, wordlist


def _assert_adversarial_absent(text: str) -> None:
    lowered = text.lower()
    for token in ADVERSARIAL:
        assert token.lower() not in lowered, f"leaked sensitive token: {token!r}"
    assert "/Users/private-name" not in text
    assert "C:\\Users\\private-name" not in text


@pytest.fixture
def project_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = _configure_home(tmp_path, monkeypatch)
    project, wordlist = _write_project(home)
    state = resolve_app_state_paths(state_root=tmp_path / "state")
    service = SpellSyncService(state_paths=state, enable_file_logging=False)
    opts = CliOptions(wordlist=str(wordlist))
    return service, opts, project, wordlist, home


def test_support_report_json_schema(project_env) -> None:
    service, opts, *_ = project_env
    report = build_support_report(service, opts)
    payload = support_report_to_dict(report)
    assert payload["schema_version"] == 1
    assert payload["privacy"]["contains_words"] is False
    assert payload["privacy"]["paths_redacted"] is True
    assert "targets" in payload
    assert isinstance(payload["targets"], (list, tuple))


def test_support_report_text_output(project_env) -> None:
    service, opts, *_ = project_env
    report = build_support_report(service, opts)
    text = format_support_report_text(report)
    assert "Spell Sync support report" in text
    assert "Privacy" in text


def test_support_report_no_words_or_config(project_env) -> None:
    service, opts, *_ = project_env
    report = build_support_report(service, opts)
    serialized = json.dumps(support_report_to_dict(report), sort_keys=True)
    _assert_adversarial_absent(serialized)
    _assert_adversarial_absent(format_support_report_text(report))


def test_support_report_path_redaction(project_env) -> None:
    service, opts, project, _, home = project_env
    report = build_support_report(service, opts)
    payload = json.dumps(support_report_to_dict(report))
    assert str(home) not in payload
    assert str(project) not in payload
    assert "/Users/private-name" not in payload


def test_export_support_report_atomic_and_collision(project_env, tmp_path: Path) -> None:
    service, opts, *_ = project_env
    report = build_support_report(service, opts)
    output = tmp_path / "support-report.json"
    export_support_report(report, output_path=output, fmt="json")
    assert output.is_file()
    with pytest.raises(FileExistsError):
        export_support_report(report, output_path=output, fmt="json")

    root = tmp_path / "state"
    first_json = default_support_report_path(state_root=root, fmt="json")
    first_json.write_text("{}", encoding="utf-8")
    second_json = default_support_report_path(state_root=root, fmt="json")
    assert second_json.suffix == ".json"
    assert second_json != first_json

    first_txt = default_support_report_path(state_root=root, fmt="text")
    first_txt.write_text("existing", encoding="utf-8")
    second_txt = default_support_report_path(state_root=root, fmt="text")
    assert second_txt.suffix == ".txt"
    assert second_txt != first_txt


def test_export_support_report_write_failure(project_env, tmp_path: Path, monkeypatch) -> None:
    service, opts, *_ = project_env
    report = build_support_report(service, opts)
    output = tmp_path / "nested" / "report.json"

    def fail_replace(self, target):  # type: ignore[no-untyped-def]
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError):
        export_support_report(report, output_path=output, fmt="json")
    assert not output.is_file()


def test_cli_support_report_stdout(project_env, monkeypatch: pytest.MonkeyPatch) -> None:
    service, opts, *_ = project_env
    monkeypatch.setattr(
        "spell_sync.support_report_cmd.build_support_report",
        lambda *_args, **_kwargs: build_support_report(service, opts),
    )
    code = cmd_support_report(opts)
    assert code == 0


def test_cli_support_report_output(
    project_env,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, opts, *_ = project_env
    monkeypatch.setattr(
        "spell_sync.support_report_cmd.build_support_report",
        lambda *_args, **_kwargs: build_support_report(service, opts),
    )
    output = tmp_path / "handoff.json"
    code = cmd_support_report(
        CliOptions(
            wordlist=opts.wordlist,
            support_report_format="json",
            support_report_output=str(output),
        )
    )
    assert code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    _assert_adversarial_absent(json.dumps(payload))


def test_path_redaction_helpers() -> None:
    home = Path("/Users/alice")
    assert redact_path("/Users/alice/Library/Spelling/LocalDictionary", home=home) == (
        "~/Library/Spelling/LocalDictionary"
    )
    assert redact_path("/external/private/location/dictionary.txt", home=home) == (
        "<external>/dictionary.txt"
    )
    windows_path = "C:\\Users\\alice\\AppData\\Local\\dict.txt"
    assert redact_path(windows_path, home=home) == "<external>/dict.txt"
    assert "user@example.com" not in redact_text("Contact user@example.com for help", home=home)


def test_support_report_subprocess(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = _configure_home(tmp_path, monkeypatch)
    project, wordlist = _write_project(home)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["HOME"] = str(home)
    if not is_macos():
        env["XDG_CONFIG_HOME"] = str(home / ".config")
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "spell_sync",
            "support-report",
            "-C",
            str(wordlist),
            "--format",
            "json",
        ],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    _assert_adversarial_absent(proc.stdout)
