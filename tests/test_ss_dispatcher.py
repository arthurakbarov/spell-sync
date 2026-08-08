"""Maintainer ss/dev command dispatcher."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.ss import _resolve_command_line, main

ROOT = Path(__file__).resolve().parents[1]


def test_resolve_placeholder_from_extra() -> None:
    assert _resolve_command_line(
        "python3 scripts/dev_runs.py show <run-id>",
        ["abc123"],
    ) == ["python3", "scripts/dev_runs.py", "show", "abc123"]


def test_ss_list_exits_zero(capsys) -> None:
    assert main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "edit-loop" in out
    assert "recovery-smoke" in out


def test_ss_unknown_command() -> None:
    assert main(["no-such-command"]) == 2


def test_dev_commands_include_recovery_and_runs_index() -> None:
    payload = json.loads((ROOT / "config" / "dev-commands.json").read_text(encoding="utf-8"))
    commands = payload["commands"]
    assert "recovery-smoke" in commands
    assert "runs-index" in commands
    assert "run_recovery_smoke.py" in commands["recovery-smoke"]["command"]
