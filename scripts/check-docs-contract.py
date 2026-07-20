#!/usr/bin/env python3
"""Documentation contract guards for spell-sync."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK_ID = "DOCS-CONTRACT"

BANNED_ACTIVE = [
    (re.compile(r"\ballow_new_project_wizard\b"), "allow_new_project_wizard"),
    (re.compile(r"\bOperationSource\b"), "OperationSource"),
    (re.compile(r"\bConfigCheckRequest\b"), "ConfigCheckRequest"),
    (re.compile(r"\bLintRequest\b"), "LintRequest"),
    (re.compile(r"\bconfig_check_request\s*\("), "config_check_request()"),
    (re.compile(r"\blint_request\s*\("), "lint_request()"),
]

EXCLUDE_PATH_PARTS = (
    ".pytest_cache/",
    "build/",
    "dist/",
    "spell_sync.egg-info/",
)

HISTORICAL_MARKERS = (
    "Removed unused",
    "removed unused",
    "Phase 3 (explicit runtime) not started",
    "Phase 3 is **not** started",
    "Historical context",
    "historical context",
    "resolved",
)

IMPLEMENTATION_TRACKER = ROOT / "docs" / "ARCHITECTURE_0_3_IMPLEMENTATION.md"
CURRENT_PHASE_HEADING = "## Current phase"
HISTORICAL_DOC_PATHS = frozenset(
    {
        "docs/UX_0_2_IMPLEMENTATION.md",
        "docs/MANUAL_TESTING.md",
        "docs/TEST_REPORT_TEMPLATE.md",
    }
)


def _project_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = data.get("project", {}).get("version")
    if not isinstance(version, str):
        raise RuntimeError("pyproject.toml missing project.version")
    return version


def _tracked_markdown() -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "*.md"],
        check=True,
        capture_output=True,
    )
    paths: list[Path] = []
    for raw in out.stdout.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8")
        if rel.startswith(".cursor/"):
            continue
        paths.append(ROOT / rel)
    return paths


def _agents_cli_commands() -> set[str]:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    fence = re.search(
        r"```text agent-config-cli-commands\s*\n(.*?)```",
        agents,
        re.DOTALL,
    )
    if not fence:
        raise RuntimeError("AGENTS.md missing agent-config-cli-commands fence")
    body = fence.group(1)
    return {
        token.strip().strip("`").strip("'").strip('"')
        for token in body.replace(",", " ").split()
        if token.strip()
    }


def _line_has_historical_context(lines: list[str], line_no: int) -> bool:
    start = max(0, line_no - 6)
    end = min(len(lines), line_no + 5)
    window = "\n".join(lines[start:end])
    return any(marker in window for marker in HISTORICAL_MARKERS)


def _fail(
    check: str,
    path: Path | None,
    *,
    line_no: int | None = None,
    detail: str,
    remediation: str,
) -> None:
    loc = str(path.relative_to(ROOT)) if path else "-"
    line_part = f"\n  line: {line_no}" if line_no is not None else ""
    print(
        f"[{CHECK_ID}-{check}]\n"
        f"  path: {loc}{line_part}\n"
        f"  contract: documentation contract violation\n"
        f"  actual: {detail}\n"
        f"  remediation: {remediation}",
        file=sys.stderr,
    )


def _check_current_phase_section() -> int:
    errors = 0
    if not IMPLEMENTATION_TRACKER.is_file():
        _fail(
            "PHASE-001",
            IMPLEMENTATION_TRACKER,
            detail="implementation tracker missing",
            remediation="restore docs/ARCHITECTURE_0_3_IMPLEMENTATION.md",
        )
        return 1
    text = IMPLEMENTATION_TRACKER.read_text(encoding="utf-8")
    headings = [
        idx
        for idx, line in enumerate(text.splitlines(), start=1)
        if line.strip() == CURRENT_PHASE_HEADING
    ]
    if len(headings) != 1:
        _fail(
            "PHASE-002",
            IMPLEMENTATION_TRACKER,
            detail=f"expected exactly one {CURRENT_PHASE_HEADING}, found {len(headings)}",
            remediation="keep a single current phase section in the implementation tracker",
        )
        errors += 1
        return errors
    start = text.index(CURRENT_PHASE_HEADING)
    body = text[start : start + 600]
    if re.search(r"Phase\s*3\s+(?:is\s+)?complete", body, re.I):
        _fail(
            "PHASE-003",
            IMPLEMENTATION_TRACKER,
            detail="implementation tracker claims Phase 3 complete",
            remediation="Phase 3 remains future work until explicit runtime lands",
        )
        errors += 1
    body_normalized = body.lower().replace("\n", " ")
    if "Phase 3" in body and "not started" not in body_normalized:
        _fail(
            "PHASE-004",
            IMPLEMENTATION_TRACKER,
            detail="Phase 3 status must explicitly say not started",
            remediation="document Phase 3 as not started until migration begins",
        )
        errors += 1
    return errors


def _check_stale_version_claims(version: str) -> int:
    errors = 0
    stale = re.compile(r"\b0\.2\.0\b")
    for path in _tracked_markdown():
        rel = str(path.relative_to(ROOT))
        if rel in HISTORICAL_DOC_PATHS or rel == "docs/ARCHITECTURE_0_3_IMPLEMENTATION.md":
            continue
        if any(part in rel for part in EXCLUDE_PATH_PARTS):
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for line_no, line in enumerate(lines, start=1):
            if stale.search(line) and _line_has_historical_context(lines, line_no - 1):
                continue
            if stale.search(line):
                _fail(
                    "VERSION-001",
                    path,
                    line_no=line_no,
                    detail=line.strip(),
                    remediation=f"update version references to {version}",
                )
                errors += 1
    return errors


def main() -> int:
    errors = 0
    version = _project_version()
    cli_commands = _agents_cli_commands()
    code_commands: set[str] = set()
    cli_file = ROOT / "spell_sync" / "cli.py"
    tree = ast.parse(cli_file.read_text(encoding="utf-8"))
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "COMMANDS"
        ):
            if isinstance(node.value, ast.Dict):
                code_commands = {
                    key.value
                    for key in node.value.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                }
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "COMMANDS"
                    and isinstance(node.value, ast.Dict)
                ):
                    code_commands = {
                        key.value
                        for key in node.value.keys
                        if isinstance(key, ast.Constant) and isinstance(key.value, str)
                    }
    if cli_commands != code_commands:
        _fail(
            "CLI-001",
            ROOT / "AGENTS.md",
            detail=f"fence={sorted(cli_commands)} code={sorted(code_commands)}",
            remediation="sync AGENTS.md agent-config-cli-commands with spell_sync/cli.py COMMANDS",
        )
        errors += 1

    for path in _tracked_markdown():
        rel = str(path.relative_to(ROOT))
        if rel in HISTORICAL_DOC_PATHS:
            continue
        if any(part in rel for part in EXCLUDE_PATH_PARTS):
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for line_no, line in enumerate(lines, start=1):
            for pattern, label in BANNED_ACTIVE:
                if not pattern.search(line):
                    continue
                if _line_has_historical_context(lines, line_no - 1):
                    continue
                _fail(
                    "API-001",
                    path,
                    line_no=line_no,
                    detail=label,
                    remediation=f"use the current API or mark the section historical ({label})",
                )
                errors += 1

    agent_dev = ROOT / "docs" / "AGENT_DEVELOPMENT.md"
    if not agent_dev.is_file():
        _fail(
            "AGENT-001",
            agent_dev,
            detail="missing docs/AGENT_DEVELOPMENT.md",
            remediation="add the agent development contract",
        )
        errors += 1

    errors += _check_current_phase_section()
    errors += _check_stale_version_claims(version)

    if errors:
        print(f"[{CHECK_ID}] failed checks: {errors}", file=sys.stderr)
        return 1
    print(
        f"[{CHECK_ID}] documentation contract OK ({len(_tracked_markdown())} markdown files, version {version})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
