"""Behavioral tests for scripts/check-agent-config.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = REPO_ROOT / "scripts" / "check-agent-config.py"


def _load_validator_module():
    spec = importlib.util.spec_from_file_location("check_agent_config", VALIDATOR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def validator():
    return _load_validator_module()


def test_current_public_configuration_passes(validator) -> None:
    errors = validator.validate_agent_config(REPO_ROOT)
    assert errors == []


def test_private_path_in_rule_fails(validator, tmp_path: Path) -> None:
    rules = tmp_path / ".cursor" / "rules"
    rules.mkdir(parents=True)
    (rules / "bad.mdc").write_text(
        "---\ndescription: bad\nalwaysApply: true\n---\nUse /Users/example/project\n",
        encoding="utf-8",
    )
    (tmp_path / "spell_sync").mkdir()
    (tmp_path / "spell_sync" / "cli.py").write_text(
        "COMMANDS = {'init': None}\n",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "## CLI commands (1)\n```text agent-config-cli-commands\n`init`\n```\n",
        encoding="utf-8",
    )
    (tmp_path / ".cursor" / "skills").mkdir()

    errors = validator.validate_agent_config(tmp_path)
    assert any("private path" in err for err in errors)


def test_private_path_in_skill_fails(validator, tmp_path: Path) -> None:
    skill_dir = tmp_path / ".cursor" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo\n---\n"
        "# Demo\n\n## When to use\nx\n\n## Do not use\ny\n\n~/code/private\n",
        encoding="utf-8",
    )
    (tmp_path / ".cursor" / "rules").mkdir()
    (tmp_path / "spell_sync").mkdir()
    (tmp_path / "spell_sync" / "cli.py").write_text(
        "COMMANDS = {'init': None}\n",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "## CLI commands (1)\n```text agent-config-cli-commands\n`init`\n```\n",
        encoding="utf-8",
    )

    errors = validator.validate_agent_config(tmp_path)
    assert any("private path" in err for err in errors)


def test_repository_relative_path_passes_private_scan(validator) -> None:
    assert validator.scan_private_paths("Use spell_sync/cli.py and tests/tui/") == []


def test_missing_command_detected(validator, tmp_path: Path) -> None:
    (tmp_path / ".cursor" / "rules").mkdir(parents=True)
    (tmp_path / ".cursor" / "skills").mkdir()
    (tmp_path / "spell_sync").mkdir()
    (tmp_path / "spell_sync" / "cli.py").write_text(
        "COMMANDS = {'init': None, 'pull': None}\n",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "## CLI commands (1)\n```text agent-config-cli-commands\n`init`\n```\n",
        encoding="utf-8",
    )

    errors = validator.validate_agent_config(tmp_path)
    assert any("missing CLI commands" in err and "pull" in err for err in errors)


def test_extra_command_detected(validator, tmp_path: Path) -> None:
    (tmp_path / ".cursor" / "rules").mkdir(parents=True)
    (tmp_path / ".cursor" / "skills").mkdir()
    (tmp_path / "spell_sync").mkdir()
    (tmp_path / "spell_sync" / "cli.py").write_text(
        "COMMANDS = {'init': None}\n",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "## CLI commands (2)\n```text agent-config-cli-commands\n`init`, `extra`\n```\n",
        encoding="utf-8",
    )

    errors = validator.validate_agent_config(tmp_path)
    assert any("extra CLI commands" in err and "extra" in err for err in errors)


def test_duplicate_command_detected(validator) -> None:
    text = "```text agent-config-cli-commands\n`init`, `init`\n```\n"
    commands, issues = validator.parse_documented_commands(text)
    assert commands == {"init"}
    assert any("duplicate CLI commands" in issue for issue in issues)


def test_stale_version_detected(validator) -> None:
    hits = validator.scan_stale("Local version 0.1.0 during development")
    assert "stale version 0.1.0" in hits


def test_skill_name_mismatch_detected(validator, tmp_path: Path) -> None:
    skill_dir = tmp_path / ".cursor" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: other\ndescription: demo\n---\n"
        "# Demo\n\n## When to use\nx\n\n## Do not use\ny\n",
        encoding="utf-8",
    )
    (tmp_path / ".cursor" / "rules").mkdir()
    (tmp_path / "spell_sync").mkdir()
    (tmp_path / "spell_sync" / "cli.py").write_text(
        "COMMANDS = {'init': None}\n",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "## CLI commands (1)\n```text agent-config-cli-commands\n`init`\n```\n",
        encoding="utf-8",
    )

    errors = validator.validate_agent_config(tmp_path)
    assert any("name 'other' != folder 'demo'" in err for err in errors)


@pytest.mark.parametrize(
    "path",
    [
        "wordlist.txt",
        "spell-sync.toml",
        "lint-whitelist.txt",
        "operation-history.jsonl",
        "snapshots/push.json",
    ],
)
def test_forbidden_personal_root_files(validator, path: str) -> None:
    reason = validator.forbidden_tracked_path(path)
    assert reason is not None


@pytest.mark.parametrize(
    "path",
    [
        "spell_sync/bundled/lint-whitelist.txt",
        "spell_sync/bundled/spell-sync.toml.example",
        "spell_sync/bundled/wordlist.txt.example",
        "spell_sync/push_journal.py",
        "spell_sync/journal_schema.py",
        "tests/test_push_journal.py",
    ],
)
def test_allowed_bundled_and_journal_paths(validator, path: str) -> None:
    assert validator.forbidden_tracked_path(path) is None


def test_marked_path_must_exist(validator, tmp_path: Path) -> None:
    skill_dir = tmp_path / ".cursor" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo\n---\n"
        "# Demo\n\n## When to use\nx\n\n## Do not use\ny\n\n"
        "```text agent-config-paths\n"
        "missing/file.py\n"
        "```\n",
        encoding="utf-8",
    )
    (tmp_path / ".cursor" / "rules").mkdir()
    (tmp_path / "spell_sync").mkdir()
    (tmp_path / "spell_sync" / "cli.py").write_text(
        "COMMANDS = {'init': None}\n",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "## CLI commands (1)\n```text agent-config-cli-commands\n`init`\n```\n",
        encoding="utf-8",
    )

    errors = validator.validate_agent_config(tmp_path)
    assert any("marked path does not exist: missing/file.py" in err for err in errors)
