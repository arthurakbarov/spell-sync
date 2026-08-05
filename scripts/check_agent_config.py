#!/usr/bin/env python3
"""Validate tracked Cursor agent configuration in the public spell-sync repository."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

MAX_RULE_LINES = 120
CLI_COMMANDS_FENCE = "agent-config-cli-commands"
AGENT_PATHS_FENCE = "agent-config-paths"
FENCE_BLOCK = re.compile(
    r"```(?:text\s+)?(" + CLI_COMMANDS_FENCE + r"|" + AGENT_PATHS_FENCE + r")\s*\n(.*?)```",
    re.DOTALL,
)

STALE_PATTERNS = [
    (re.compile(r"\b0\.1\.0\b"), "stale version 0.1.0"),
    (re.compile(r"Python\s+3\.9", re.I), "stale Python 3.9 policy"),
    (re.compile(r"CLI only", re.I), "stale CLI-only public interface claim"),
    (re.compile(r"daily\.sh"), "maintainer daily.sh reference"),
    (re.compile(r"sync-tool\.sh"), "maintainer sync-tool.sh reference"),
    (re.compile(r"first stable.*1\.0\.0", re.I), "stale 1.0.0 release plan"),
    (re.compile(r"explicit runtime is Phase", re.I), "stale explicit-runtime deferral"),
    (re.compile(r"still implicit in 0\.2\.1", re.I), "stale implicit runtime claim"),
    (re.compile(r"ContextVar\).*0\.2\.1", re.I), "stale ContextVar runtime claim"),
]
PRIVATE_PATH_PATTERNS = [
    re.compile(r"~/code/"),
    re.compile(r"/Users/"),
    re.compile(r"/home/[^/\s]+/"),
    re.compile(r"spell-words\.git"),
    re.compile(r"arthurakbarov/spell-words"),
]
# Absolute maintainer-home paths must not appear in tracked scripts/tests (privacy fixtures
# may use generic /Users/… names; only the maintainer identity is forbidden).
_MAINTAINER_USER = "arthur" + "akbarov"
MAINTAINER_ABSOLUTE_PATH_PATTERNS = [
    re.compile(rf"/Users/{re.escape(_MAINTAINER_USER)}\b"),
    re.compile(rf"/home/{re.escape(_MAINTAINER_USER)}\b"),
]
PUBLISH_PATTERN = re.compile(
    r"\b(git push|force-push|force push|gh release|twine upload|PyPI publish|tag v?\d)"
    r"|push to (origin|public|upstream|remote)",
    re.I,
)
GUARD_PATTERN = re.compile(r"explicit.*(request|approval|owner|ask)", re.I)
COMMAND_TOKEN = re.compile(r"`([a-z][a-z0-9-]*)`")

FORBIDDEN_ROOT_FILES = {
    "wordlist.txt",
    "spell-sync.toml",
    "lint-whitelist.txt",
    "operation-history.jsonl",
    "operation-history.lock",
}
ALLOWED_BUNDLED_RESOURCES = {
    "spell_sync/bundled/lint-whitelist.txt",
    "spell_sync/bundled/spell-sync.toml.example",
    "spell_sync/bundled/wordlist.txt.example",
}
FORBIDDEN_STATE_ROOT_DIRS = {
    "snapshots",
    "journal",
}

REQUIRED_RULES = (
    "agent-workflow.mdc",
    "project-safety.mdc",
    "architecture-boundaries.mdc",
    "tests-fixtures.mdc",
    "test-efficiency.mdc",
)

REQUIRED_SKILLS = (
    "execute-current-phase",
    "apply-phase-fixes",
    "advance-current-phase",
    "architecture-refactor",
    "diagnostics-change",
    "spell-sync-ci",
    "mutation-safety-audit",
    "select-and-run-tests",
    "autonomous-work",
    "project-development",
    "repository-workflow",
    "git-change-management",
    "security-audit",
    "preflight-publish",
)

BANNED_WORKFLOW_TERMS = [
    (re.compile(r"\breview\s+zip\b", re.I), "review ZIP"),
    (re.compile(r"\bUPLOAD_THIS_FILE\b"), "UPLOAD_THIS_FILE"),
    (re.compile(r"\bupload handoff\b", re.I), "upload handoff"),
    (re.compile(r"\bexternal reviewer\b", re.I), "external reviewer"),
    (re.compile(r"\bexternal review\b", re.I), "external review"),
    (re.compile(r"\barchive handoff\b", re.I), "archive handoff"),
    (re.compile(r"\bAI assistant\b", re.I), "AI assistant"),
    (re.compile(r"\bchat prompt\b", re.I), "chat prompt"),
]

MODIFYING_SKILLS = (
    "execute-current-phase",
    "apply-phase-fixes",
    "advance-current-phase",
    "architecture-refactor",
    "diagnostics-change",
    "release-candidate",
    "spell-sync-ci",
    "add-target",
    "tui-flow",
)

FOCUSED_TEST_SKILL = "select-and-run-tests"
TESTING_STRATEGY_DOC = "docs/TESTING_STRATEGY.md"
TEST_IMPACT_REGISTRY = "tests/test-impact.toml"
TEST_PLAN_SCRIPT = "scripts/test_plan.py"
FOCUSED_RUNNER_SCRIPT = "scripts/run_focused_tests.py"

BASELINE_FULL_CI_PATTERN = re.compile(
    r"run `scripts/ci\.sh` when baseline|"
    r"run `scripts/ci\.sh` before starting|"
    r"baseline CI fails\)|"
    r"must run `scripts/ci\.sh` before",
    re.I,
)
FOCUSED_SKILL_FORBIDDEN_CI = re.compile(
    r"(?<!\bnot )(?<!\bwithout )scripts/ci\.sh",
    re.I,
)
SNAPSHOT_FORCE_REQUIRED = re.compile(r"--force")
SNAPSHOT_REPORT_FOOTER = re.compile(r"CODE_ARCHIVE")

PYTHON311_PATTERN = re.compile(r"python3\.11")
BARE_PYTHON_SCRIPTS = re.compile(r"(?<![\w.])python scripts/")
BARE_PYTHON_BACKTICK_CMD = re.compile(r"`python\s")
HYPHENATED_CHECK_TOKEN = re.compile(r"`(check-[a-z0-9-]+(?:\.[a-z0-9-]+)*)`")
ALLOWED_HYPHENATED_CHECK_TOKENS = frozenset(
    {
        "check-docs-style.sh",
    }
)
SNAPSHOT_EVIDENCE_REQUIRED = "check_ci_evidence"
SNAPSHOT_L1_TOKENS = ("run_dev_loop", "commit-gate", "L1", "purpose local")

SNAPSHOT_FINALIZATION_MARKER = "Finalize workspace snapshot"

TIMESTAMPED_ARCHIVE_PATTERN = re.compile(
    r"code[-_]\d{4}[-_]\d{2}[-_]\d{2}|code-\d+\.zip",
    re.I,
)

OWNER_SNAPSHOT_FORBIDDEN_IN_PUBLIC = re.compile(
    r"create-code-snapshot\.py|OWNER_WORKSPACE_SNAPSHOT",
)

FINAL_CI_LIFECYCLE_SKILLS = (
    "execute-current-phase",
    "apply-phase-fixes",
    "architecture-refactor",
    "diagnostics-change",
    "spell-sync-ci",
)

STALE_CI_THEN_COMMIT = re.compile(
    r"After green CI[\s\S]{0,200}?\bcommit",
    re.IGNORECASE,
)


def _parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end].strip()
    data: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def _expected_commands(cli_file: Path) -> set[str]:
    tree = ast.parse(cli_file.read_text(encoding="utf-8"))
    for node in tree.body:
        value: ast.expr | None = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "COMMANDS":
                value = node.value
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "COMMANDS":
                    value = node.value
                    break
        if value is not None and isinstance(value, ast.Dict):
            return {
                k.value
                for k in value.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
    raise RuntimeError(f"Could not parse COMMANDS from {cli_file}")


def parse_documented_commands(text: str) -> tuple[set[str] | None, list[str]]:
    match = FENCE_BLOCK.search(text)
    if not match or match.group(1) != CLI_COMMANDS_FENCE:
        return None, ["AGENTS.md: missing marked CLI command block"]
    block = match.group(2)
    commands = COMMAND_TOKEN.findall(block)
    if not commands:
        commands = [line.strip() for line in block.splitlines() if line.strip()]
    issues: list[str] = []
    if not commands:
        issues.append("AGENTS.md: marked CLI command block is empty")
        return set(), issues
    duplicates = sorted({cmd for cmd in commands if commands.count(cmd) > 1})
    if duplicates:
        joined = ", ".join(duplicates)
        issues.append(f"AGENTS.md: duplicate CLI commands in marked block: {joined}")
    return set(commands), issues


def parse_marked_paths(text: str, source: str) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    paths: list[str] = []
    for match in FENCE_BLOCK.finditer(text):
        if match.group(1) != AGENT_PATHS_FENCE:
            continue
        for line in match.group(2).splitlines():
            candidate = line.strip().strip("-").strip()
            if candidate:
                paths.append(candidate)
    return paths, issues


def scan_private_paths(text: str) -> list[str]:
    hits: list[str] = []
    for pattern in PRIVATE_PATH_PATTERNS:
        if pattern.search(text):
            hits.append("private path or topology reference")
            break
    return hits


def scan_maintainer_absolute_paths(text: str) -> list[str]:
    hits: list[str] = []
    for pattern in MAINTAINER_ABSOLUTE_PATH_PATTERNS:
        if pattern.search(text):
            hits.append("maintainer absolute path")
            break
    return hits


def check_scripts_and_tests_maintainer_paths(root: Path) -> list[str]:
    errors: list[str] = []
    for base_name in ("scripts", "tests"):
        base = root / base_name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            rel = path.relative_to(root).as_posix()
            for label in scan_maintainer_absolute_paths(text):
                errors.append(f"{rel}: contains {label}")
    return errors


def scan_stale(text: str) -> list[str]:
    hits: list[str] = []
    for pattern, label in STALE_PATTERNS:
        if pattern.search(text):
            hits.append(label)
    return hits


def check_persistent_git_stash(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "stash", "list"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    if result.stdout.strip():
        return ["[AGENT-WORKFLOW-GIT-004] persistent Git stash remains after task completion"]
    return []


def git_ls_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def forbidden_tracked_path(path: str) -> str | None:
    normalized = path.replace("\\", "/")
    if normalized in ALLOWED_BUNDLED_RESOURCES:
        return None
    parts = Path(normalized).parts
    if not parts:
        return None
    if len(parts) == 1:
        name = parts[0]
        if name in FORBIDDEN_ROOT_FILES:
            return f"forbidden personal root file: {normalized}"
        if name.endswith(".log"):
            return f"forbidden log file at repo root: {normalized}"
        if name in FORBIDDEN_STATE_ROOT_DIRS:
            return f"forbidden generated state directory at repo root: {normalized}"
    if parts[0] in FORBIDDEN_STATE_ROOT_DIRS:
        return f"forbidden generated state path: {normalized}"
    if Path(normalized).name in {"operation-history.jsonl", "operation-history.lock"}:
        return f"forbidden operation history artifact: {normalized}"
    return None


def check_tracked_forbidden_files(root: Path) -> list[str]:
    errors: list[str] = []
    for tracked in git_ls_files(root):
        reason = forbidden_tracked_path(tracked)
        if reason:
            errors.append(f"tracked file policy violation: {reason}")
    return errors


def scan_banned_workflow_terms(text: str) -> list[str]:
    hits: list[str] = []
    for pattern, label in BANNED_WORKFLOW_TERMS:
        if pattern.search(text):
            hits.append(label)
    return hits


def scan_timestamped_archive_names(text: str) -> list[str]:
    if TIMESTAMPED_ARCHIVE_PATTERN.search(text):
        return ["timestamped owner archive name"]
    return []


def check_snapshot_tooling_absent_from_public_package(root: Path) -> list[str]:
    errors: list[str] = []
    for rel in git_ls_files(root):
        if OWNER_SNAPSHOT_FORBIDDEN_IN_PUBLIC.search(rel):
            errors.append(f"snapshot tooling must not ship in public package: {rel}")
    wheel_paths = [root / "spell_sync", root / "scripts"]
    for base in wheel_paths:
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_file() and "create-code-snapshot" in path.name:
                errors.append(
                    "snapshot script must not live in public package tree: "
                    f"{path.relative_to(root)}"
                )
    return errors


def check_test_efficiency_contract(root: Path) -> list[str]:
    errors: list[str] = []
    strategy = root / TESTING_STRATEGY_DOC
    if not strategy.is_file():
        errors.append(
            f"[TEST-EFFICIENCY-001] missing {TESTING_STRATEGY_DOC}; add docs/TESTING_STRATEGY.md"
        )
    registry = root / TEST_IMPACT_REGISTRY
    if not registry.is_file():
        errors.append(
            f"[TEST-EFFICIENCY-002] missing {TEST_IMPACT_REGISTRY}; add tests/test-impact.toml"
        )
    for rel in (TEST_PLAN_SCRIPT, FOCUSED_RUNNER_SCRIPT):
        if not (root / rel).is_file():
            errors.append(f"[TEST-EFFICIENCY-003] missing {rel}")
    return errors


def check_modifying_skill_validation(root: Path) -> list[str]:
    errors: list[str] = []
    skills = root / ".cursor" / "skills"
    focused = skills / FOCUSED_TEST_SKILL / "SKILL.md"
    if focused.is_file():
        focused_text = focused.read_text(encoding="utf-8")
        if FOCUSED_SKILL_FORBIDDEN_CI.search(focused_text):
            errors.append(
                f"[TEST-EFFICIENCY-004] .cursor/skills/{FOCUSED_TEST_SKILL}/SKILL.md "
                "must not invoke full CI"
            )
    for skill_name in MODIFYING_SKILLS:
        skill_file = skills / skill_name / "SKILL.md"
        if not skill_file.is_file():
            continue
        text = skill_file.read_text(encoding="utf-8")
        if BASELINE_FULL_CI_PATTERN.search(text):
            errors.append(
                f"[TEST-EFFICIENCY-005] .cursor/skills/{skill_name}/SKILL.md "
                "requires baseline full CI for every clean task; use CI evidence reuse"
            )
        if skill_name in {"execute-current-phase", "apply-phase-fixes", "architecture-refactor"}:
            if "select-and-run-tests" not in text:
                errors.append(
                    f"[TEST-EFFICIENCY-006] .cursor/skills/{skill_name}/SKILL.md "
                    "must reference select-and-run-tests staged validation"
                )
    return errors


def _snapshot_section(text: str) -> str | None:
    marker = SNAPSHOT_FINALIZATION_MARKER
    if marker not in text:
        return None
    start = text.index(marker)
    rest = text[start:]
    # section runs until next markdown H2 or EOF
    nxt = re.search(r"\n## ", rest[len(marker) :])
    if nxt:
        return rest[: len(marker) + nxt.start()]
    return rest


def check_snapshot_finalization_skills(root: Path) -> list[str]:
    errors: list[str] = []
    skills = root / ".cursor" / "skills"
    for skill_name in MODIFYING_SKILLS:
        skill_file = skills / skill_name / "SKILL.md"
        if not skill_file.is_file():
            continue
        text = skill_file.read_text(encoding="utf-8")
        rel = skill_file.relative_to(root)
        section = _snapshot_section(text)
        if section is None:
            errors.append(
                f"[SNAPSHOT-001] {rel}: modifying skill missing "
                f"'{SNAPSHOT_FINALIZATION_MARKER}' section"
            )
            continue
        if SNAPSHOT_EVIDENCE_REQUIRED not in section and not any(
            token in section for token in SNAPSHOT_L1_TOKENS
        ):
            errors.append(
                f"[SNAPSHOT-008] {rel}: snapshot finalization must reference "
                "L1/run_dev_loop or check_ci_evidence (when L2 ran)"
            )
        if not SNAPSHOT_FORCE_REQUIRED.search(section):
            errors.append(
                f"[SNAPSHOT-002] {rel}: snapshot finalization must require "
                "create-code-snapshot --force"
            )
        if not SNAPSHOT_REPORT_FOOTER.search(section):
            errors.append(
                f"[SNAPSHOT-003] {rel}: snapshot finalization must require "
                "CODE_ARCHIVE report footer"
            )
        if "when recreation was required" in section.lower():
            errors.append(
                f"[SNAPSHOT-004] {rel}: do not gate snapshot on optional recreation; "
                "always before report"
            )
    agent_dev = root / "docs" / "AGENT_DEVELOPMENT.md"
    if agent_dev.is_file():
        text = agent_dev.read_text(encoding="utf-8")
        if "## Workspace snapshot" not in text:
            errors.append(
                "[SNAPSHOT-005] docs/AGENT_DEVELOPMENT.md missing Workspace snapshot section"
            )
        if "no hash sidecar file" not in text and "no sidecar file" not in text:
            errors.append(
                "[SNAPSHOT-007] docs/AGENT_DEVELOPMENT.md must state SHA256 is "
                "response-only (no sidecar file on disk)"
            )
    agents_md = root / "AGENTS.md"
    if agents_md.is_file():
        text = agents_md.read_text(encoding="utf-8")
        if "docs/AGENT_DEVELOPMENT.md` § Workspace snapshot" not in text:
            errors.append(
                "[SNAPSHOT-006] AGENTS.md must reference "
                "docs/AGENT_DEVELOPMENT.md § Workspace snapshot"
            )
    return errors


def check_final_ci_lifecycle(root: Path) -> list[str]:
    errors: list[str] = []
    evidence_script = root / "scripts" / "check_ci_evidence.py"
    if not evidence_script.is_file():
        errors.append(
            "[CI-LIFECYCLE-001] missing scripts/check_ci_evidence.py final evidence verifier"
        )
    plan_steps = root / "scripts" / "test_selection" / "plan_steps.py"
    if not plan_steps.is_file():
        errors.append(
            "[CI-LIFECYCLE-002] missing scripts/test_selection/plan_steps.py run-key contract"
        )
    resolved_runtime = root / "spell_sync" / "resolved_runtime.py"
    if resolved_runtime.is_file():
        text = resolved_runtime.read_text(encoding="utf-8")
        if re.search(r"^def build_resolved_runtime\b", text, re.MULTILINE):
            errors.append(
                "[CI-LIFECYCLE-003] spell_sync/resolved_runtime.py must not export "
                "build_resolved_runtime; use private _build_resolved_runtime"
            )
    skills = root / ".cursor" / "skills"
    for skill_name in FINAL_CI_LIFECYCLE_SKILLS:
        skill_file = skills / skill_name / "SKILL.md"
        if not skill_file.is_file():
            continue
        text = skill_file.read_text(encoding="utf-8")
        rel = skill_file.relative_to(root)
        if "check_ci_evidence.py" not in text and "check_ci_necessity.py" not in text:
            errors.append(
                f"[CI-LIFECYCLE-004] {rel}: modifying lifecycle skill must reference "
                "check_ci_necessity.py and/or check_ci_evidence.py"
            )
        if STALE_CI_THEN_COMMIT.search(text):
            errors.append(
                f"[CI-LIFECYCLE-005] {rel}: full CI must not precede commit "
                "(remove 'After green CI' then commit ordering)"
            )
        if (
            "scripts/ci.sh" in text
            and "committed HEAD" not in text
            and "--purpose publish" not in text
        ):
            errors.append(
                f"[CI-LIFECYCLE-006] {rel}: run full CI only on committed HEAD "
                "after clean verification (L2 / --purpose publish)"
            )
    agent_dev = root / "docs" / "AGENT_DEVELOPMENT.md"
    if agent_dev.is_file():
        text = agent_dev.read_text(encoding="utf-8")
        if "check_ci_evidence.py" not in text:
            errors.append(
                "[CI-LIFECYCLE-007] docs/AGENT_DEVELOPMENT.md must document "
                "scripts/check_ci_evidence.py"
            )
        if "--purpose local" not in text or "--purpose publish" not in text:
            errors.append(
                "[CI-LIFECYCLE-008] docs/AGENT_DEVELOPMENT.md must document "
                "check_ci_necessity --purpose local|publish (L2 only for publish)"
            )
    return errors


def check_cursor_command_hygiene(root: Path) -> list[str]:
    """Reject stale interpreters and hyphenated check-* script aliases in Cursor config."""
    errors: list[str] = []
    cursor = root / ".cursor"
    if not cursor.is_dir():
        return errors
    paths = sorted(list(cursor.rglob("*.md")) + list(cursor.rglob("*.mdc")))
    for path in paths:
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(root)
        if PYTHON311_PATTERN.search(text):
            errors.append(f"[AGENT-CMD-001] {rel}: forbidden python3.11; use python3")
        if BARE_PYTHON_SCRIPTS.search(text):
            errors.append(
                f"[AGENT-CMD-002] {rel}: bare 'python scripts/...' forbidden; use python3"
            )
        if BARE_PYTHON_BACKTICK_CMD.search(text):
            errors.append(
                f"[AGENT-CMD-003] {rel}: bare '`python ...' command forbidden; use python3"
            )
        for match in HYPHENATED_CHECK_TOKEN.finditer(text):
            token = match.group(1)
            if token in ALLOWED_HYPHENATED_CHECK_TOKENS:
                continue
            if token.endswith(".sh"):
                continue
            errors.append(
                f"[AGENT-CMD-004] {rel}: hyphenated check token `{token}` forbidden; "
                "use python3 scripts/check_*.py"
            )
    return errors


def check_agents_skill_index(root: Path) -> list[str]:
    """Require AGENTS.md to mention each .cursor/skills/ directory."""
    errors: list[str] = []
    skills = root / ".cursor" / "skills"
    agents = root / "AGENTS.md"
    if not skills.is_dir() or not agents.is_file():
        return errors
    text = agents.read_text(encoding="utf-8")
    for skill_dir in sorted(p for p in skills.iterdir() if p.is_dir()):
        name = skill_dir.name
        if name not in text:
            errors.append(f"[AGENT-SKILL-INDEX-001] AGENTS.md must mention skill `{name}`")
    return errors


def validate_agent_config(root: Path) -> list[str]:
    errors: list[str] = []
    errors.extend(check_test_efficiency_contract(root))
    errors.extend(check_modifying_skill_validation(root))
    errors.extend(check_snapshot_finalization_skills(root))
    errors.extend(check_final_ci_lifecycle(root))
    errors.extend(check_cursor_command_hygiene(root))
    errors.extend(check_agents_skill_index(root))
    cursor = root / ".cursor"
    rules = cursor / "rules"
    skills = cursor / "skills"
    cli_file = root / "spell_sync" / "cli.py"
    agents = root / "AGENTS.md"

    if (root / ".cursorrules").exists():
        errors.append(".cursorrules is forbidden — use .cursor/rules/*.mdc")

    if not cli_file.is_file():
        errors.append(f"missing {cli_file.relative_to(root)}")
        return errors

    expected_cli = _expected_commands(cli_file)
    errors.extend(check_tracked_forbidden_files(root))
    errors.extend(check_snapshot_tooling_absent_from_public_package(root))

    if not rules.is_dir():
        errors.append("missing .cursor/rules/")
    else:
        present_rules = {path.name for path in rules.glob("*.mdc")}
        for required in REQUIRED_RULES:
            if required not in present_rules:
                errors.append(f"missing required rule: .cursor/rules/{required}")
        for path in sorted(rules.glob("*.mdc")):
            text = path.read_text(encoding="utf-8")
            rel = path.relative_to(root)
            fm = _parse_frontmatter(text)
            if "description" not in fm:
                errors.append(f"{rel}: missing description in frontmatter")
            if fm.get("alwaysApply") != "true" and "globs" not in fm:
                errors.append(f"{rel}: needs alwaysApply or globs")
            if len(text.splitlines()) > MAX_RULE_LINES:
                errors.append(f"{rel}: exceeds {MAX_RULE_LINES} lines")
            for label in scan_stale(text):
                errors.append(f"{rel}: contains {label}")
            for label in scan_banned_workflow_terms(text):
                errors.append(f"{rel}: contains banned workflow term ({label})")
            for label in scan_timestamped_archive_names(text):
                errors.append(f"{rel}: contains {label}")
            for _ in scan_private_paths(text):
                errors.append(f"{rel}: contains private path or topology reference")

    if not skills.is_dir():
        errors.append("missing .cursor/skills/")
    else:
        present_skills = {path.name for path in skills.iterdir() if path.is_dir()}
        for required in REQUIRED_SKILLS:
            if required not in present_skills:
                errors.append(f"missing required skill: .cursor/skills/{required}/SKILL.md")
        names: dict[str, Path] = {}
        for skill_dir in sorted(p for p in skills.iterdir() if p.is_dir()):
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.is_file():
                errors.append(f"missing {skill_dir.relative_to(root)}/SKILL.md")
                continue
            text = skill_file.read_text(encoding="utf-8")
            rel = skill_file.relative_to(root)
            fm = _parse_frontmatter(text)
            name = fm.get("name", "")
            if not name:
                errors.append(f"{rel}: missing name")
            elif name != skill_dir.name:
                errors.append(f"{rel}: name '{name}' != folder '{skill_dir.name}'")
            if "description" not in fm:
                errors.append(f"{rel}: missing description")
            if "disable-model-invocation" in text.lower():
                errors.append(f"{rel}: disable-model-invocation forbidden")
            if name in names:
                errors.append(f"duplicate skill name '{name}'")
            else:
                names[name] = skill_file
            for label in scan_stale(text):
                errors.append(f"{rel}: contains {label}")
            for label in scan_banned_workflow_terms(text):
                errors.append(f"{rel}: contains banned workflow term ({label})")
            for label in scan_timestamped_archive_names(text):
                errors.append(f"{rel}: contains {label}")
            for _ in scan_private_paths(text):
                errors.append(f"{rel}: contains private path or topology reference")
            if PUBLISH_PATTERN.search(text) and not GUARD_PATTERN.search(text):
                errors.append(f"{rel}: publish/push/tag without explicit-request guard")
            if "When to use" not in text:
                errors.append(f"{rel}: missing 'When to use' section")
            if "Do not use" not in text:
                errors.append(f"{rel}: missing 'Do not use' section")
            if skill_dir.name in MODIFYING_SKILLS:
                if SNAPSHOT_FINALIZATION_MARKER not in text:
                    errors.append(
                        f"{rel}: modifying skill missing '{SNAPSHOT_FINALIZATION_MARKER}' section"
                    )
                if skill_dir.name != "release-candidate" and re.search(
                    r"git archive.*owner|owner.*git archive",
                    text,
                    re.I,
                ):
                    errors.append(f"{rel}: git archive forbidden for owner workspace snapshot")
            marked_paths, path_issues = parse_marked_paths(text, str(rel))
            errors.extend(path_issues)
            for marked in marked_paths:
                if not (root / marked).is_file():
                    errors.append(f"{rel}: marked path does not exist: {marked}")

        if (skills / "spell-sync-stale-audit").exists():
            errors.append("remove obsolete skill spell-sync-stale-audit")

    agent_dev = root / "docs" / "AGENT_DEVELOPMENT.md"
    if not agent_dev.is_file():
        errors.append("missing docs/AGENT_DEVELOPMENT.md")
    git_workflow = root / "docs" / "GIT-WORKFLOW.md"
    if not git_workflow.is_file():
        errors.append("missing docs/GIT-WORKFLOW.md")
    elif "ends with" not in git_workflow.read_text(encoding="utf-8"):
        errors.append("docs/GIT-WORKFLOW.md must document trailing-period commit subjects")

    if agents.is_file():
        text = agents.read_text(encoding="utf-8")
        rel = agents.relative_to(root)
        for label in scan_stale(text):
            errors.append(f"{rel}: contains {label}")
        for label in scan_banned_workflow_terms(text):
            errors.append(f"{rel}: contains banned workflow term ({label})")
        for _ in scan_private_paths(text):
            errors.append(f"{rel}: contains private path or topology reference")
        documented, cli_issues = parse_documented_commands(text)
        errors.extend(cli_issues)
        if documented is not None:
            missing = sorted(expected_cli - documented)
            extra = sorted(documented - expected_cli)
            if missing:
                joined = ", ".join(missing)
                errors.append(f"AGENTS.md: missing CLI commands in marked block: {joined}")
            if extra:
                joined = ", ".join(extra)
                errors.append(f"AGENTS.md: extra CLI commands in marked block: {joined}")
            count_match = re.search(r"## CLI commands \((\d+)\)", text)
            if count_match is None:
                errors.append("AGENTS.md: missing CLI command count heading")
            else:
                declared = int(count_match.group(1))
                actual = len(documented)
                if declared != actual:
                    errors.append(
                        f"AGENTS.md: CLI command count mismatch "
                        f"(heading {declared}, marked block {actual})"
                    )
                if declared != len(expected_cli):
                    errors.append(
                        f"AGENTS.md: CLI command count mismatch "
                        f"(heading {declared}, parser {len(expected_cli)})"
                    )
        marked_paths, path_issues = parse_marked_paths(text, str(rel))
        errors.extend(path_issues)
        for marked in marked_paths:
            if not (root / marked).is_file():
                errors.append(f"{rel}: marked path does not exist: {marked}")
    else:
        errors.append("missing AGENTS.md")

    errors.extend(check_persistent_git_stash(root))
    errors.extend(check_scripts_and_tests_maintainer_paths(root))

    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = validate_agent_config(root)
    if errors:
        print("Agent configuration check FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("Agent configuration OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
