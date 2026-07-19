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
]
PRIVATE_PATH_PATTERNS = [
    re.compile(r"~/code/"),
    re.compile(r"/Users/"),
    re.compile(r"/home/[^/\s]+/"),
    re.compile(r"spell-words\.git"),
    re.compile(r"arthurakbarov/spell-words"),
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


def scan_stale(text: str) -> list[str]:
    hits: list[str] = []
    for pattern, label in STALE_PATTERNS:
        if pattern.search(text):
            hits.append(label)
    return hits


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


def validate_agent_config(root: Path) -> list[str]:
    errors: list[str] = []
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

    if not rules.is_dir():
        errors.append("missing .cursor/rules/")
    else:
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
            for _ in scan_private_paths(text):
                errors.append(f"{rel}: contains private path or topology reference")

    if not skills.is_dir():
        errors.append("missing .cursor/skills/")
    else:
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
            for _ in scan_private_paths(text):
                errors.append(f"{rel}: contains private path or topology reference")
            if PUBLISH_PATTERN.search(text) and not GUARD_PATTERN.search(text):
                errors.append(f"{rel}: publish/push/tag without explicit-request guard")
            if "When to use" not in text:
                errors.append(f"{rel}: missing 'When to use' section")
            if "Do not use" not in text:
                errors.append(f"{rel}: missing 'Do not use' section")
            marked_paths, path_issues = parse_marked_paths(text, str(rel))
            errors.extend(path_issues)
            for marked in marked_paths:
                if not (root / marked).is_file():
                    errors.append(f"{rel}: marked path does not exist: {marked}")

        if (skills / "spell-sync-stale-audit").exists():
            errors.append("remove obsolete skill spell-sync-stale-audit")

    if agents.is_file():
        text = agents.read_text(encoding="utf-8")
        rel = agents.relative_to(root)
        for label in scan_stale(text):
            errors.append(f"{rel}: contains {label}")
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
