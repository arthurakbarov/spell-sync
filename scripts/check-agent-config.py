#!/usr/bin/env python3
"""Validate tracked Cursor agent configuration in the public spell-sync repository."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURSOR = ROOT / ".cursor"
RULES = CURSOR / "rules"
SKILLS = CURSOR / "skills"
CLI_FILE = ROOT / "spell_sync" / "cli.py"

MAX_RULE_LINES = 120
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


def _expected_commands() -> set[str]:
    tree = ast.parse(CLI_FILE.read_text(encoding="utf-8"))
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
    raise RuntimeError("Could not parse COMMANDS from spell_sync/cli.py")


def _check_rules(errors: list[str]) -> None:
    if not RULES.is_dir():
        errors.append("missing .cursor/rules/")
        return
    for path in sorted(RULES.glob("*.mdc")):
        text = path.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        if "description" not in fm:
            errors.append(f"{path.relative_to(ROOT)}: missing description in frontmatter")
        if fm.get("alwaysApply") != "true" and "globs" not in fm:
            errors.append(f"{path.relative_to(ROOT)}: needs alwaysApply or globs")
        if len(text.splitlines()) > MAX_RULE_LINES:
            errors.append(f"{path.relative_to(ROOT)}: exceeds {MAX_RULE_LINES} lines")
        _scan_stale(path, text, errors)


def _check_skills(errors: list[str], expected_cli: set[str]) -> None:
    if not SKILLS.is_dir():
        errors.append("missing .cursor/skills/")
        return
    names: dict[str, Path] = {}
    for skill_dir in sorted(p for p in SKILLS.iterdir() if p.is_dir()):
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            errors.append(f"missing {skill_dir.relative_to(ROOT)}/SKILL.md")
            continue
        text = skill_file.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        name = fm.get("name", "")
        if not name:
            errors.append(f"{skill_file.relative_to(ROOT)}: missing name")
        elif name != skill_dir.name:
            errors.append(
                f"{skill_file.relative_to(ROOT)}: name '{name}' != folder '{skill_dir.name}'"
            )
        if "description" not in fm:
            errors.append(f"{skill_file.relative_to(ROOT)}: missing description")
        if "disable-model-invocation" in text.lower():
            errors.append(f"{skill_file.relative_to(ROOT)}: disable-model-invocation forbidden")
        if name in names:
            errors.append(f"duplicate skill name '{name}'")
        else:
            names[name] = skill_file
        _scan_stale(skill_file, text, errors)
        _scan_private_paths(skill_file, text, errors)
        if PUBLISH_PATTERN.search(text) and not GUARD_PATTERN.search(text):
            errors.append(
                f"{skill_file.relative_to(ROOT)}: publish/push/tag without explicit-request guard"
            )
        if "When to use" not in text:
            errors.append(f"{skill_file.relative_to(ROOT)}: missing 'When to use' section")
        if "Do not use" not in text:
            errors.append(f"{skill_file.relative_to(ROOT)}: missing 'Do not use' section")
    _check_cli_docs(errors, expected_cli)


def _check_cli_docs(errors: list[str], expected_cli: set[str]) -> None:
    agents = ROOT / "AGENTS.md"
    if agents.is_file():
        text = agents.read_text(encoding="utf-8")
        _scan_stale(agents, text, errors)
        _scan_private_paths(agents, text, errors)
        for cmd in sorted(expected_cli):
            if cmd not in text:
                errors.append(f"AGENTS.md: missing CLI command '{cmd}'")
    stale_audit = SKILLS / "spell-sync-stale-audit"
    if stale_audit.exists():
        errors.append("remove obsolete skill spell-sync-stale-audit")


def _scan_stale(path: Path, text: str, errors: list[str]) -> None:
    rel = path.relative_to(ROOT)
    for pattern, label in STALE_PATTERNS:
        if pattern.search(text):
            errors.append(f"{rel}: contains {label}")


def _scan_private_paths(path: Path, text: str, errors: list[str]) -> None:
    rel = path.relative_to(ROOT)
    for pattern in PRIVATE_PATH_PATTERNS:
        if pattern.search(text):
            errors.append(f"{rel}: contains private path or topology reference")


def main() -> int:
    errors: list[str] = []
    if (ROOT / ".cursorrules").exists():
        errors.append(".cursorrules is forbidden — use .cursor/rules/*.mdc")
    expected_cli = _expected_commands()
    _check_rules(errors)
    _check_skills(errors, expected_cli)
    if errors:
        print("Agent configuration check FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("Agent configuration OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
