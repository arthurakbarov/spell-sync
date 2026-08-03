"""Behavioral tests for scripts/check_agent_config.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import check_agent_config  # noqa: E402

VALIDATOR_PATH = REPO_ROOT / "scripts" / "check_agent_config.py"


@pytest.fixture(scope="module")
def validator():
    return check_agent_config


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


def test_required_skills_present(validator) -> None:
    errors = validator.validate_agent_config(REPO_ROOT)
    assert not any("missing required skill" in err for err in errors)


def test_banned_workflow_term_detected(validator) -> None:
    hits = validator.scan_banned_workflow_terms("Upload handoff via review ZIP")
    assert hits


def test_persistent_git_stash_fails(validator, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=ci@test",
            "-c",
            "user.name=ci",
            "commit",
            "--allow-empty",
            "-qm",
            "init",
        ],
        cwd=repo,
        check=True,
    )
    (repo / "wip.txt").write_text("wip\n", encoding="utf-8")
    subprocess.run(["git", "add", "wip.txt"], cwd=repo, check=True)
    subprocess.run(["git", "stash", "push", "-m", "wip"], cwd=repo, check=True)
    errors = validator.check_persistent_git_stash(repo)
    assert errors == ["[AGENT-WORKFLOW-GIT-004] persistent Git stash remains after task completion"]


def test_python311_in_skill_fails(validator, tmp_path: Path) -> None:
    skill_dir = tmp_path / ".cursor" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo\n---\n"
        "# Demo\n\n## When to use\nx\n\n## Do not use\ny\n\n"
        "python3.11 scripts/check_agent_config.py\n",
        encoding="utf-8",
    )
    (tmp_path / ".cursor" / "rules").mkdir(exist_ok=True)
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
    assert any("python3.11" in err for err in errors)


def test_bare_python_scripts_fails(validator, tmp_path: Path) -> None:
    rules = tmp_path / ".cursor" / "rules"
    rules.mkdir(parents=True)
    (rules / "bad.mdc").write_text(
        "---\ndescription: bad\nalwaysApply: true\n---\nRun python scripts/foo.py\n",
        encoding="utf-8",
    )
    (tmp_path / ".cursor" / "skills").mkdir()
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
    assert any("AGENT-CMD-002" in err for err in errors)


def test_hyphenated_check_token_detected(validator) -> None:
    text = "when `check-ci-necessity` requires it"
    match = validator.HYPHENATED_CHECK_TOKEN.search(text)
    assert match is not None
    assert match.group(1) == "check-ci-necessity"
    assert match.group(1) not in validator.ALLOWED_HYPHENATED_CHECK_TOKENS


def test_hyphenated_check_sh_allowed(validator, tmp_path: Path) -> None:
    rules = tmp_path / ".cursor" / "rules"
    rules.mkdir(parents=True)
    (rules / "ok.mdc").write_text(
        "---\ndescription: ok\nalwaysApply: true\n---\nRun `check-docs-style.sh` when needed.\n",
        encoding="utf-8",
    )
    (tmp_path / ".cursor" / "skills").mkdir()
    errors = validator.check_cursor_command_hygiene(tmp_path)
    assert errors == []


def test_snapshot_section_requires_check_ci_evidence(validator, tmp_path: Path) -> None:
    skill_dir = tmp_path / ".cursor" / "skills" / "tui-flow"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: tui-flow\ndescription: demo\n---\n"
        "# Demo\n\n## When to use\nx\n\n## Do not use\ny\n\n"
        "## Finalize workspace snapshot\n\n"
        "skill create-code-snapshot with --force; footer CODE_ARCHIVE\n",
        encoding="utf-8",
    )
    errors = validator.check_snapshot_finalization_skills(tmp_path)
    assert any("SNAPSHOT-008" in err for err in errors)


def test_agents_skill_index_requires_all_skills(validator, tmp_path: Path) -> None:
    skills = tmp_path / ".cursor" / "skills"
    (skills / "alpha").mkdir(parents=True)
    (skills / "beta").mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text("Mentions alpha only\n", encoding="utf-8")
    errors = validator.check_agents_skill_index(tmp_path)
    assert any("beta" in err for err in errors)
