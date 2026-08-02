#!/usr/bin/env python3
"""Documentation contract guards for spell-sync."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
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
    "Historical context",
    "historical context",
    "resolved",
)

IMPLEMENTATION_TRACKER = "docs/ARCHITECTURE_0_3_IMPLEMENTATION.md"
CURRENT_PHASE_HEADING = "## Current phase"
ARCHITECTURE_STATUS_START = "[architecture-status:start]"
ARCHITECTURE_STATUS_END = "[architecture-status:end]"
_PHASE_SECTION_HEADING = re.compile(r"^## Phase (\d+[a-z]?)(?: — |: )", re.MULTILINE)
KNOWN_STATUSES = frozenset(
    {"complete", "in-progress", "not-started", "planned", "awaiting-approval", "blocked"}
)
AGENT_WORKFLOW_DOCS = (
    "AGENTS.md",
    "docs/AGENT_DEVELOPMENT.md",
    "docs/TESTING_STRATEGY.md",
    ".cursor/skills/spell-sync-ci/SKILL.md",
)
TESTING_STRATEGY_DOC = Path("docs/TESTING_STRATEGY.md")
PINNED_PYTHON = re.compile(r"python3\.\d+")
DEVELOPMENT_VERSION = Path("docs/DEVELOPMENT.md")
HISTORICAL_DOC_PATHS = frozenset(
    {
        "docs/MANUAL_TESTING.md",
        "docs/TEST_REPORT_TEMPLATE.md",
    }
)


@dataclass(frozen=True, slots=True)
class ContractViolation:
    check_id: str
    path: Path | None
    line_no: int | None
    detail: str
    remediation: str


def _project_version(root: Path) -> str:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = data.get("project", {}).get("version")
    if not isinstance(version, str):
        raise RuntimeError("pyproject.toml missing project.version")
    return version


def _tracked_markdown(root: Path) -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "*.md"],
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
        paths.append(root / rel)
    return paths


def _agents_cli_commands(root: Path) -> set[str]:
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
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


def _current_phase_body(text: str) -> tuple[int | None, str]:
    lines = text.splitlines()
    heading_indexes = [
        idx for idx, line in enumerate(lines) if line.strip() == CURRENT_PHASE_HEADING
    ]
    if len(heading_indexes) != 1:
        return None, ""
    start = heading_indexes[0] + 1
    body_lines: list[str] = []
    for line in lines[start:]:
        if line.startswith("## ") and line.strip() != CURRENT_PHASE_HEADING:
            break
        if line.strip() == ARCHITECTURE_STATUS_START:
            break
        body_lines.append(line)
    return heading_indexes[0] + 1, "\n".join(body_lines).strip()


def _parse_architecture_status(text: str) -> tuple[dict[str, str] | None, str | None]:
    start_count = text.count(ARCHITECTURE_STATUS_START)
    end_count = text.count(ARCHITECTURE_STATUS_END)
    if start_count == 0 and end_count == 0:
        return None, None
    if start_count != 1 or end_count != 1:
        return None, "architecture status markers must appear exactly once"
    start = text.index(ARCHITECTURE_STATUS_START) + len(ARCHITECTURE_STATUS_START)
    end = text.index(ARCHITECTURE_STATUS_END)
    block = text[start:end].strip()
    statuses: dict[str, str] = {}
    for line_no, raw in enumerate(block.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            return None, f"invalid architecture status line {line_no}: {line!r}"
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            return None, f"invalid architecture status line {line_no}: {line!r}"
        if key in statuses:
            return None, f"duplicate architecture status key: {key}"
        statuses[key] = value
    return statuses, None


def _check_current_phase_section(root: Path) -> list[ContractViolation]:
    tracker = root / IMPLEMENTATION_TRACKER
    violations: list[ContractViolation] = []
    if not tracker.is_file():
        return [
            ContractViolation(
                "PHASE-001",
                tracker,
                None,
                "implementation tracker missing",
                "restore docs/ARCHITECTURE_0_3_IMPLEMENTATION.md",
            )
        ]
    text = tracker.read_text(encoding="utf-8")
    heading_line, body = _current_phase_body(text)
    heading_count = sum(1 for line in text.splitlines() if line.strip() == CURRENT_PHASE_HEADING)
    if heading_count != 1:
        violations.append(
            ContractViolation(
                "PHASE-002",
                tracker,
                None,
                f"expected exactly one {CURRENT_PHASE_HEADING}, found {heading_count}",
                "keep a single current phase section in the implementation tracker",
            )
        )
        return violations
    if not body:
        violations.append(
            ContractViolation(
                "PHASE-003",
                tracker,
                heading_line,
                "current phase section body is empty",
                "document the active phase status in the current phase section",
            )
        )

    statuses, parse_error = _parse_architecture_status(text)
    if parse_error:
        violations.append(
            ContractViolation(
                "PHASE-004",
                tracker,
                None,
                parse_error,
                "fix architecture-status marker block formatting",
            )
        )
        return violations
    if statuses is None:
        return violations

    current = statuses.get("current")
    if not current:
        violations.append(
            ContractViolation(
                "PHASE-005",
                tracker,
                None,
                "architecture status missing current phase",
                "add current: <phase-id> to architecture-status block",
            )
        )
    phase_keys = [key for key in statuses if key != "current"]
    if current and current not in phase_keys:
        violations.append(
            ContractViolation(
                "PHASE-006",
                tracker,
                None,
                f"current references unknown phase id: {current}",
                "add a matching phase entry in architecture-status block",
            )
        )

    in_progress = [
        key for key, value in statuses.items() if key != "current" and value == "in-progress"
    ]
    if len(in_progress) > 1:
        violations.append(
            ContractViolation(
                "PHASE-007",
                tracker,
                None,
                f"multiple in-progress phases: {in_progress}",
                "mark at most one phase as in-progress",
            )
        )

    for key, value in statuses.items():
        if key == "current":
            continue
        if value not in KNOWN_STATUSES:
            violations.append(
                ContractViolation(
                    "PHASE-008",
                    tracker,
                    None,
                    f"unknown status for {key}: {value}",
                    f"use one of {sorted(KNOWN_STATUSES)}",
                )
            )

    if current and current in statuses and statuses[current] == "complete":
        violations.append(
            ContractViolation(
                "PHASE-009",
                tracker,
                None,
                f"current phase points to completed phase: {current}",
                "set current to not-started, in-progress, awaiting-approval, or blocked",
            )
        )

    awaiting_non_current = [
        key
        for key, value in statuses.items()
        if key != "current" and key != current and value == "awaiting-approval"
    ]
    current_awaiting = bool(current and statuses.get(current) == "awaiting-approval")
    if len(awaiting_non_current) > 1 or (awaiting_non_current and current_awaiting):
        violations.append(
            ContractViolation(
                "PHASE-010",
                tracker,
                None,
                "multiple awaiting-approval phases",
                "mark at most one phase as awaiting-approval",
            )
        )
    elif awaiting_non_current:
        violations.append(
            ContractViolation(
                "PHASE-011",
                tracker,
                None,
                f"awaiting-approval phase must be current: {awaiting_non_current}",
                "set current to the awaiting-approval phase id",
            )
        )

    if in_progress and current and statuses.get(current) != "in-progress":
        violations.append(
            ContractViolation(
                "PHASE-012",
                tracker,
                None,
                f"in-progress phase must be current: {in_progress}",
                "set current to the in-progress phase id",
            )
        )

    return violations


_CORRECTIVE_IN_PROGRESS = re.compile(
    r"corrective work[^.\n]{0,120}:\s*in progress\b",
    re.IGNORECASE,
)
_PHASE10_SECTION = re.compile(
    r"## Phase 10 — Version 0\.3\.0(.*?)(?=^## |\Z)",
    re.MULTILINE | re.DOTALL,
)
_OWNER_APPROVED_CLAIM = re.compile(
    r"owner[- ]approved|owner approval recorded",
    re.IGNORECASE,
)
_RELEASE_PUBLISHED_CLAIM = re.compile(
    r"\b(released|published|tagged)\b",
    re.IGNORECASE,
)
_STALE_PHASE10_HEAD = re.compile(r"\b9069783\b")


def _check_phase_tracker_readiness(root: Path) -> list[ContractViolation]:
    """P1–P6: phase-10 approval-readiness consistency guards."""
    tracker = root / IMPLEMENTATION_TRACKER
    violations: list[ContractViolation] = []
    if not tracker.is_file():
        return violations
    text = tracker.read_text(encoding="utf-8")
    statuses, parse_error = _parse_architecture_status(text)
    if parse_error or statuses is None:
        return violations

    _, current_body = _current_phase_body(text)
    if _CORRECTIVE_IN_PROGRESS.search(current_body):
        violations.append(
            ContractViolation(
                "PHASE-016",
                tracker,
                None,
                "corrective work still marked in progress in current phase section",
                "mark corrective work complete when evidence is current",
            )
        )

    phase10_status = statuses.get("phase-10")
    phase10_match = _PHASE10_SECTION.search(text)
    phase10_body = phase10_match.group(1) if phase10_match else ""
    if phase10_status == "awaiting-approval":
        if _OWNER_APPROVED_CLAIM.search(phase10_body):
            violations.append(
                ContractViolation(
                    "PHASE-017",
                    tracker,
                    None,
                    "phase-10 awaiting-approval conflicts with owner-approved claim",
                    "remove owner-approved wording until owner decision is recorded",
                )
            )
        if _RELEASE_PUBLISHED_CLAIM.search(phase10_body):
            violations.append(
                ContractViolation(
                    "PHASE-018",
                    tracker,
                    None,
                    "phase-10 section claims release publication before approval",
                    "state release not performed while awaiting owner approval",
                )
            )

    last_validation = re.search(
        r"## Last validation\s*\n\s*```text\s*\n(.*?)```",
        text,
        re.DOTALL,
    )
    if last_validation:
        first_line = last_validation.group(1).strip().splitlines()[0]
        if first_line.lower().startswith("phase 10"):
            if _STALE_PHASE10_HEAD.search(first_line):
                violations.append(
                    ContractViolation(
                        "PHASE-019",
                        tracker,
                        None,
                        "last validation Phase 10 line references stale HEAD 9069783",
                        "update Phase 10 validation line to current product HEAD "
                        "or mark historical",
                    )
                )
            if phase10_status == "awaiting-approval" and "awaiting" not in first_line.lower():
                violations.append(
                    ContractViolation(
                        "PHASE-020",
                        tracker,
                        None,
                        "last validation Phase 10 line missing awaiting-approval semantics",
                        "document Phase 10 as awaiting owner approval",
                    )
                )

    if (
        phase10_status == "awaiting-approval"
        and statuses.get("current") == "phase-10"
        and "implementation **complete**" in current_body
        and "awaiting owner approval" in current_body.lower()
    ):
        pass
    elif phase10_status == "awaiting-approval" and statuses.get("current") == "phase-10":
        if "implementation **complete**" not in current_body:
            violations.append(
                ContractViolation(
                    "PHASE-021",
                    tracker,
                    None,
                    "phase-10 awaiting approval without implementation-complete note",
                    "document implementation complete while owner approval is pending",
                )
            )

    return violations


def _phase_section_index(text: str) -> dict[str, list[int]]:
    sections: dict[str, list[int]] = {}
    for match in _PHASE_SECTION_HEADING.finditer(text):
        phase_id = f"phase-{match.group(1).lower()}"
        line_no = text[: match.start()].count("\n") + 1
        sections.setdefault(phase_id, []).append(line_no)
    return sections


def _check_architecture_phase_sections(root: Path) -> list[ContractViolation]:
    tracker = root / IMPLEMENTATION_TRACKER
    violations: list[ContractViolation] = []
    if not tracker.is_file():
        return violations
    text = tracker.read_text(encoding="utf-8")
    statuses, parse_error = _parse_architecture_status(text)
    if parse_error or statuses is None:
        return violations

    sections = _phase_section_index(text)
    for phase_id, line_numbers in sections.items():
        if len(line_numbers) <= 1:
            continue
        violations.append(
            ContractViolation(
                "PHASE-013",
                tracker,
                line_numbers[1],
                f"duplicate architecture phase section: {phase_id}",
                f"keep one canonical section for {phase_id}",
            )
        )

    current = statuses.get("current")
    for key, value in statuses.items():
        if key == "current":
            continue
        if value == "awaiting-approval" and key not in sections:
            violations.append(
                ContractViolation(
                    "PHASE-014",
                    tracker,
                    None,
                    f"awaiting-approval phase missing section: {key}",
                    f"add ## Phase section for {key}",
                )
            )

    if current and current.startswith("phase-"):
        suffix = current.removeprefix("phase-")
        if suffix.isdigit():
            next_id = f"phase-{int(suffix) + 1}"
            if statuses.get(next_id) == "not-started" and next_id not in sections:
                violations.append(
                    ContractViolation(
                        "PHASE-015",
                        tracker,
                        None,
                        f"not-started next phase missing section: {next_id}",
                        f"add ## Phase section for {next_id}",
                    )
                )

    return violations


def _ci_summary_schema(root: Path) -> int:
    ci_runner = root / "scripts" / "ci_runner.py"
    text = ci_runner.read_text(encoding="utf-8")
    match = re.search(r"^SUMMARY_SCHEMA\s*=\s*(\d+)", text, re.MULTILINE)
    if not match:
        raise RuntimeError("scripts/ci_runner.py missing SUMMARY_SCHEMA")
    return int(match.group(1))


def _check_agent_workflow_docs(root: Path) -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    schema: int | None = None
    ci_runner = root / "scripts" / "ci_runner.py"
    if ci_runner.is_file():
        schema = _ci_summary_schema(root)
    agent_dev = root / "docs" / "AGENT_DEVELOPMENT.md"
    if schema is not None and agent_dev.is_file():
        text = agent_dev.read_text(encoding="utf-8")
        if re.search(r"schema version 1\b", text, re.IGNORECASE):
            violations.append(
                ContractViolation(
                    "AGENT-002",
                    agent_dev,
                    None,
                    "AGENT_DEVELOPMENT.md documents schema version 1",
                    f"document CI summary schema version {schema}",
                )
            )
        schema_ok = (
            f"schema version {schema}" in text.lower() or f"schema v{schema}" in text.lower()
        )
        if not schema_ok:
            violations.append(
                ContractViolation(
                    "AGENT-003",
                    agent_dev,
                    None,
                    f"AGENT_DEVELOPMENT.md missing schema version {schema}",
                    (
                        "document schemaVersion, runId, historyLogPath, "
                        "historySummaryPath, failedCheckId"
                    ),
                )
            )

    for rel in AGENT_WORKFLOW_DOCS:
        path = root / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if rel.endswith("AGENT_DEVELOPMENT.md"):
            if "check-ci-evidence.py" not in text:
                violations.append(
                    ContractViolation(
                        "AGENT-006",
                        path,
                        None,
                        "missing check-ci-evidence.py reference",
                        "document final evidence verification after full CI on committed HEAD",
                    )
                )
            if (
                re.search(
                    r"(?:Run full CI|scripts/ci\.sh)[\s\S]{0,300}?\bcommit",
                    text,
                    re.IGNORECASE,
                )
                and "committed HEAD" not in text
            ):
                violations.append(
                    ContractViolation(
                        "AGENT-007",
                        path,
                        None,
                        "workflow documents full CI before commit",
                        "commit tracked changes before final full CI; "
                        "verify with check-ci-evidence.py",
                    )
                )
        lines = text.splitlines()
        for line_no, line in enumerate(lines, start=1):
            if PINNED_PYTHON.search(line):
                violations.append(
                    ContractViolation(
                        "AGENT-004",
                        path,
                        line_no,
                        line.strip(),
                        "use portable python3 or PYTHON_BIN=${PYTHON_BIN:-python3}",
                    )
                )
            if "ruff" in line and ("check" in line or "format" in line):
                if "spell_sync" in line and "scripts" not in line:
                    violations.append(
                        ContractViolation(
                            "AGENT-005",
                            path,
                            line_no,
                            line.strip(),
                            "include scripts in ruff check/format examples",
                        )
                    )

    development = root / DEVELOPMENT_VERSION
    if development.is_file():
        version = _project_version(root)
        dev_lines = development.read_text(encoding="utf-8").splitlines()
        for line_no, line in enumerate(dev_lines, start=1):
            if "currently" in line.lower() and version in line:
                violations.append(
                    ContractViolation(
                        "VERSION-002",
                        development,
                        line_no,
                        line.strip(),
                        "do not duplicate current package version; reference pyproject.toml",
                    )
                )

    return violations


def _check_stale_version_claims(root: Path, version: str) -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    stale = re.compile(r"\b0\.2\.[01]\b")
    for path in _tracked_markdown(root):
        rel = str(path.relative_to(root))
        if rel in HISTORICAL_DOC_PATHS or rel == IMPLEMENTATION_TRACKER:
            continue
        if rel.startswith("docs/decisions/"):
            continue
        if any(part in rel for part in EXCLUDE_PATH_PARTS):
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for line_no, line in enumerate(lines, start=1):
            if stale.search(line) and _line_has_historical_context(lines, line_no - 1):
                continue
            if stale.search(line):
                violations.append(
                    ContractViolation(
                        "VERSION-001",
                        path,
                        line_no,
                        line.strip(),
                        f"update version references to {version}",
                    )
                )
    return violations


def _check_testing_strategy_doc(root: Path) -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    path = root / TESTING_STRATEGY_DOC
    if not path.is_file():
        violations.append(
            ContractViolation(
                "TEST-001",
                path,
                None,
                f"missing {TESTING_STRATEGY_DOC}",
                "add docs/TESTING_STRATEGY.md with Levels 0–3 validation guidance",
            )
        )
        return violations
    text = path.read_text(encoding="utf-8")
    for required in ("Level 0", "Level 1", "Level 2", "Level 3", "test-impact.toml"):
        if required not in text:
            violations.append(
                ContractViolation(
                    "TEST-002",
                    path,
                    None,
                    f"TESTING_STRATEGY.md missing section reference: {required}",
                    f"document {required} in the testing strategy",
                )
            )
    return violations


def check_repository(root: Path) -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    version = _project_version(root)
    try:
        cli_commands = _agents_cli_commands(root)
    except RuntimeError as exc:
        violations.append(
            ContractViolation(
                "CLI-002",
                root / "AGENTS.md",
                None,
                str(exc),
                "restore AGENTS.md agent-config-cli-commands fence",
            )
        )
        cli_commands = set()

    code_commands: set[str] = set()
    cli_file = root / "spell_sync" / "cli.py"
    if cli_file.is_file():
        tree = ast.parse(cli_file.read_text(encoding="utf-8"))
        for node in tree.body:
            if (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "COMMANDS"
                and isinstance(node.value, ast.Dict)
            ):
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
    if cli_commands and code_commands and cli_commands != code_commands:
        violations.append(
            ContractViolation(
                "CLI-001",
                root / "AGENTS.md",
                None,
                f"fence={sorted(cli_commands)} code={sorted(code_commands)}",
                "sync AGENTS.md agent-config-cli-commands with spell_sync/cli.py COMMANDS",
            )
        )

    for path in _tracked_markdown(root):
        rel = str(path.relative_to(root))
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
                violations.append(
                    ContractViolation(
                        "API-001",
                        path,
                        line_no,
                        label,
                        f"use the current API or mark the section historical ({label})",
                    )
                )

    agent_dev = root / "docs" / "AGENT_DEVELOPMENT.md"
    if not agent_dev.is_file():
        violations.append(
            ContractViolation(
                "AGENT-001",
                agent_dev,
                None,
                "missing docs/AGENT_DEVELOPMENT.md",
                "add the agent development contract",
            )
        )

    violations.extend(_check_current_phase_section(root))
    violations.extend(_check_phase_tracker_readiness(root))
    violations.extend(_check_architecture_phase_sections(root))
    violations.extend(_check_stale_version_claims(root, version))
    violations.extend(_check_agent_workflow_docs(root))
    violations.extend(_check_testing_strategy_doc(root))
    return violations


def format_violation(root: Path, violation: ContractViolation) -> str:
    loc = str(violation.path.relative_to(root)) if violation.path else "-"
    line_part = f"\n  line: {violation.line_no}" if violation.line_no is not None else ""
    return (
        f"[{CHECK_ID}-{violation.check_id}]\n"
        f"  path: {loc}{line_part}\n"
        f"  contract: documentation contract violation\n"
        f"  actual: {violation.detail}\n"
        f"  remediation: {violation.remediation}"
    )


def main() -> int:
    violations = check_repository(ROOT)
    if violations:
        for violation in violations:
            print(format_violation(ROOT, violation), file=sys.stderr)
        print(f"[{CHECK_ID}] failed checks: {len(violations)}", file=sys.stderr)
        return 1
    version = _project_version(ROOT)
    markdown_count = len(_tracked_markdown(ROOT))
    print(
        f"[{CHECK_ID}] documentation contract OK "
        f"({markdown_count} markdown files, version {version})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
