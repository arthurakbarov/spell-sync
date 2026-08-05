"""dev-commands registry and generated DEVELOPMENT table."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_dev_commands import (
    CI_CHECKS_END,
    CI_CHECKS_START,
    MARKER_END,
    MARKER_START,
    main,
    validate,
)

ROOT = Path(__file__).resolve().parents[1]


def test_dev_commands_validate_clean():
    assert validate() == []


def test_dev_commands_cli_default_checks_fences():
    assert main([]) == 0


def test_dev_commands_cli_check():
    assert main(["--check"]) == 0


def test_development_markers_present():
    text = (ROOT / "docs" / "DEVELOPMENT.md").read_text(encoding="utf-8")
    assert MARKER_START in text
    assert MARKER_END in text
    assert CI_CHECKS_START in text
    assert CI_CHECKS_END in text
    assert "bootstrap.python" in text
    assert "packaging.members" in text


def test_surface_covers_every_command():
    commands = json.loads((ROOT / "config" / "dev-commands.json").read_text(encoding="utf-8"))[
        "commands"
    ]
    surface = json.loads((ROOT / "config" / "dev-surface.json").read_text(encoding="utf-8"))
    listed = set(surface["ownerCommands"]) | set(surface["agentCommands"])
    assert set(commands) <= listed
    assert "install-git-hooks" in surface["agentCommands"]
    assert "preflight-publish" in surface["ownerCommands"]
    assert "preflight-publish" in surface["agentCommands"]
